import { defineConfig } from '@playwright/test';

export default defineConfig({
  webServer: [
    {
      command: `"${process.env.PYTHON_COMMAND || 'python'}" -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --log-level warning`,
      cwd: '..',
      url: 'http://127.0.0.1:8001/api/v1/health',
      reuseExistingServer: false,
      env: { APP_ENV: 'development', DEMO_MODE: 'true', GEMINI_API_KEY: '', OPENWEATHER_API_KEY: '', ENABLE_NO_KEY_WEATHER: 'false',
        DATABASE_PATH: 'backend/data/runtime/playwright.sqlite3', UPLOAD_DIR: 'backend/data/uploads/playwright' },
    },
    { command: 'npm run dev', url: 'http://127.0.0.1:5174', reuseExistingServer: false,
      env: { API_PROXY_TARGET: 'http://127.0.0.1:8001' } },
  ],
  testDir: './e2e',
  testMatch: '**/*.pw.js',
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 8_000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5174',
    browserName: 'chromium',
    headless: true,
    trace: 'retain-on-failure',
  },
});
