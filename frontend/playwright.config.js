// 文件基本信息：frontend/playwright.config.js
// 目的：启动本地后端/前端并执行真实浏览器 E2E。
// 输入：Playwright 测试文件和本地 Python/Vite 服务。
// 输出：浏览器 E2E 报告；真实 HFSS 用例不在本地伪造。
// 维护：E2E 服务、端口或证据规则变化时同步验收场景和 frontend/e2e 索引。

import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    {
      command: 'py -3.12 -m backend.server',
      cwd: '..',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: true,
      timeout: 30_000,
      env: {
        ARRAYLAB_PROFILE: 'development',
        ARRAYLAB_HFSS_MODE: 'stub',
        ARRAYLAB_PREDICTOR_MODE: 'stub',
        ARRAYLAB_DB_PATH: path.join(os.tmpdir(), 'arraylab-e2e.sqlite3'),
        ARRAYLAB_DATA_ROOT: path.join(os.tmpdir(), 'arraylab-e2e-data'),
      }
    },
    { command: 'npm run dev -- --host 127.0.0.1', cwd: '.', url: 'http://127.0.0.1:5173', reuseExistingServer: true, timeout: 30_000 }
  ]
})
