import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5173',
  },
  webServer: [
    {
      command:
        'cd .. && APP_AUTO_LOAD_DOTENV=0 LLM_PROVIDER=fake ASR_PROVIDER=fake PRON_PROVIDER=mock TTS_PROVIDER=browser python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
      timeout: 20_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 20_000,
    },
  ],
});
