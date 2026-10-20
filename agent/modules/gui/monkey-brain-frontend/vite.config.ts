/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const pipelinePort = process.env.PIPELINE_PORT || process.env.VITE_PIPELINE_PORT || '8000'
const agentPort = process.env.AGENT_PORT || process.env.VITE_AGENT_BACKEND_PORT || '8100'
const devHost = process.env.VITE_DEV_HOST || '127.0.0.1'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  root: '.',
  server: {
    port: Number(process.env.VITE_DEV_PORT || process.env.PORT || 5173),
    host: devHost,
    strictPort: true, // 端口由启动脚本选择并锁定
    allowedHosts: ['primatex.pku.edu.cn'],
    hmr: {
      overlay: false,
    },
    fs: {
      strict: true
    },
    // Development server only. Public deployments should serve dist/ through Nginx.
    cors: false,
    open: false,     // 服务器环境不自动打开浏览器
    proxy: {
      '/api/agent': {
        target: `http://127.0.0.1:${agentPort}`,
        changeOrigin: true,
      },
      '/api': {
        target: `http://127.0.0.1:${pipelinePort}`,
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'antd', 'zustand', 'axios'],
    exclude: ['niivue']
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    exclude: ['node_modules', 'dist', '.git', '.cache'],
  },
})
