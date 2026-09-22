import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_postgres_connection(db_session: AsyncSession) -> None:
    assert await db_session.scalar(text("SELECT 1")) == 1
