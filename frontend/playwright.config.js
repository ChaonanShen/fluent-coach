import { defineConfig } from '@playwright/test';

const backendPort = process.env.E2E_BACKEND_PORT || '8000';
const frontendPort = process.env.E2E_FRONTEND_PORT || '5173';
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
        `cd .. && APP_AUTO_LOAD_DOTENV=0 LLM_PROVIDER=fake ASR_PROVIDER=fake PRON_PROVIDER=mock TTS_PROVIDER=browser python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port ${backendPort}`,
      url: `${backendUrl}/api/health`,
      reuseExistingServer: true,
      timeout: 20_000,
    },
    {
      command: `BACKEND_PORT=${backendPort} npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      url: frontendUrl,
      reuseExistingServer: true,
      timeout: 20_000,
    },
  ],
});
