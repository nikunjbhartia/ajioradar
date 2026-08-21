import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  build: {
    outDir: '../dist',
    emptyOutDir: false
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8088',
        changeOrigin: true
      }
    }
  }
});
