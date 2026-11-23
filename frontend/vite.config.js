// 文件基本信息：frontend/vite.config.js
// 目的：配置 Vue 3/Vite 开发服务器，并把 /api 代理到本地 Python 后端。
// 输入：Vite 配置环境。
// 输出：Vite 配置对象。
// 维护：修改后同步 frontend/目录索引.md、api.md 和启动说明。

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000'
    }
  }
})
