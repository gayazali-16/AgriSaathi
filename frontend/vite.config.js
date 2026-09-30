import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxyTarget = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8001';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: { '/api': apiProxyTarget, '/docs': apiProxyTarget, '/openapi.json': apiProxyTarget },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/testSetup.js',
    clearMocks: true,
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
