"""Run the deterministic 30-event reconnect benchmark against a deployed service."""

import argparse
import asyncio
import json
from collections import Counter
from typing import Any
from urllib.parse import quote, urlparse
from uuid import uuid4

import httpx
from websockets.asyncio.client import ClientConnection, connect

EVENT_COUNT = 30
INTERRUPT_AFTER = 10
MISSED_DURING_INTERRUPTION = 10


def websocket_base_url(http_base_url: str) -> str:
    parsed = urlparse(http_base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}"


async def publish(
    client: httpx.AsyncClient,
    base_url: str,
    room_id: str,
    event_number: int,
) -> dict[str, Any]:
    response = await client.post(
        f"{base_url}/api/rooms/{quote(room_id, safe='')}/updates",
        json={
            "clientId": "benchmark-producer",
            "content": f"deterministic-event-{event_number:02d}",
        },
    )
    response.raise_for_status()
    return response.json()


async def receive_update(socket: ClientConnection) -> dict[str, Any]:
    raw_message = await asyncio.wait_for(socket.recv(), timeout=15)
    envelope = json.loads(raw_message)
    if envelope.get("type") != "update" or not isinstance(envelope.get("data"), dict):
        raise RuntimeError(f"Unexpected WebSocket message: {envelope!r}")
    return envelope["data"]


async def run_benchmark(base_url: str, room_id: str) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    websocket_base = websocket_base_url(base_url)
    deliveries: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30) as client:
        initial_url = f"{websocket_base}/ws/rooms/{quote(room_id, safe='')}?after=0"
        async with connect(initial_url, open_timeout=30) as socket:
            for event_number in range(1, INTERRUPT_AFTER + 1):
                accepted = await publish(client, base_url, room_id, event_number)
                delivered = await receive_update(socket)
                if delivered != accepted:
                    raise RuntimeError(
                        "Live WebSocket event did not match the committed REST response"
                    )
                deliveries.append(delivered)

        cursor_at_interruption = int(deliveries[-1]["sequence"])
        for event_number in range(
            INTERRUPT_AFTER + 1,
            INTERRUPT_AFTER + MISSED_DURING_INTERRUPTION + 1,
        ):
            await publish(client, base_url, room_id, event_number)

        reconnect_url = (
            f"{websocket_base}/ws/rooms/{quote(room_id, safe='')}?after={cursor_at_interruption}"
        )
        async with connect(reconnect_url, open_timeout=30) as socket:
            for _ in range(MISSED_DURING_INTERRUPTION):
                deliveries.append(await receive_update(socket))

            for event_number in range(
                INTERRUPT_AFTER + MISSED_DURING_INTERRUPTION + 1,
                EVENT_COUNT + 1,
            ):
                accepted = await publish(client, base_url, room_id, event_number)
                delivered = await receive_update(socket)
                if delivered != accepted:
                    raise RuntimeError(
                        "Live WebSocket event did not match the committed REST response"
                    )
                deliveries.append(delivered)

        history_response = await client.get(
            f"{base_url}/api/rooms/{quote(room_id, safe='')}/updates",
            params={"after": 0, "limit": EVENT_COUNT},
        )
        history_response.raise_for_status()
        history = history_response.json()

    expected_content = [f"deterministic-event-{number:02d}" for number in range(1, 31)]
    observed_content = [str(event["content"]) for event in deliveries]
    delivery_ids = [str(event["updateId"]) for event in deliveries]
    id_counts = Counter(delivery_ids)
    duplicate_deliveries = sum(count - 1 for count in id_counts.values())
    missing_content = sorted(set(expected_content) - set(observed_content))
    sequences = [int(event["sequence"]) for event in deliveries]
    history_ids = [str(event["updateId"]) for event in history["updates"]]

    result = {
        "roomId": room_id,
        "expectedEventCount": EVENT_COUNT,
        "observedEventCount": len(deliveries),
        "uniqueEventCount": len(id_counts),
        "missingEventCount": len(missing_content),
        "duplicateEventCount": duplicate_deliveries,
        "ordered": sequences == sorted(sequences),
        "reconnectCount": 1,
        "cursorAtInterruption": cursor_at_interruption,
        "historyMatchesDeliveredEvents": history_ids == delivery_ids,
        "latestSequence": history["latestSequence"],
        "finalConnectionState": "connected-and-current",
        "finalRunState": "not-modeled-by-incident-feed-interpretation",
    }
    if (
        result["observedEventCount"] != EVENT_COUNT
        or result["uniqueEventCount"] != EVENT_COUNT
        or result["missingEventCount"] != 0
        or result["duplicateEventCount"] != 0
        or result["ordered"] is not True
        or result["historyMatchesDeliveredEvents"] is not True
    ):
        raise RuntimeError(json.dumps(result, indent=2))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--room", default=f"benchmark-{uuid4()}")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    report = asyncio.run(run_benchmark(arguments.base_url, arguments.room))
    print(json.dumps(report, indent=2))
