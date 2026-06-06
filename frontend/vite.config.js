import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backendPort = process.env.BACKEND_PORT || '8000';
const backendHttp = `http://127.0.0.1:${backendPort}`;
const backendWs = `ws://127.0.0.1:${backendPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': backendHttp,
      '/ws': {
        target: backendWs,
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    globals: true,
    setupFiles: './src/setupTests.js',
  },
});
