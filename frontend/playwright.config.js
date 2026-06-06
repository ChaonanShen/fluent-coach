import { defineConfig } from '@playwright/test';

const backendPort = process.env.E2E_BACKEND_PORT || '18000';
const frontendPort = process.env.E2E_FRONTEND_PORT || '15173';
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: frontendUrl,
  },
  webServer: [
    {
      command:
        `cd .. && APP_ENV_FILE=config/e2e.env python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port ${backendPort}`,
      url: `${backendUrl}/api/health`,
      reuseExistingServer: false,
      timeout: 20_000,
    },
    {
      command: `BACKEND_PORT=${backendPort} npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 20_000,
    },
  ],
});
