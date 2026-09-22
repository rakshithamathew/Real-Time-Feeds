import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const backendTarget = process.env.VITE_BACKEND_TARGET ?? 'http://127.0.0.1:8001';
const websocketTarget = backendTarget.replace(/^http/, 'ws');

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: backendTarget,
      },
      '/health': {
        target: backendTarget,
      },
      '/ws': {
        target: websocketTarget,
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    clearMocks: true,
  },
});
