// 文件基本信息：frontend/e2e/workbench.spec.js
// 目的：使用真实浏览器验证 Vue 工作台与 Python 后端 stub 的关键流程。
// 输入：临时 .aedt 路径、合法阵列 JSON、prediction 模式。
// 输出：Playwright 页面断言、任务状态和下载证据。
// 维护：页面/API/验收场景变化时同步 frontend/e2e 索引和 TASK-UI-001。

import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const e2eProject = path.resolve('..', 'e2e-demo.aedt')

test.beforeAll(() => fs.writeFileSync(e2eProject, 'playwright stub project', 'utf8'))
test.afterAll(() => { try { fs.unlinkSync(e2eProject) } catch {} })

test('binds, trains, evaluates, displays and downloads a result', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '非规则阵列方向图预测' })).toBeVisible()
  await page.getByLabel('HFSS 工程绝对路径').fill(e2eProject)
  await page.getByRole('button', { name: '绑定工程' }).click()
  await expect(page.getByText('工程绑定成功，等待开始训练。')).toBeVisible()
  await page.getByRole('button', { name: '开始训练' }).click()
  await expect(page.getByText('模型：ready')).toBeVisible({ timeout: 10_000 })
  await page.getByLabel('固定 JSON 输入（JSON 是权威来源）').fill(JSON.stringify({ unit_count: 1, units: [{ unit_id: 1, i: 1, j: 1, x: 0, y: 0 }] }))
  await page.getByRole('button', { name: '执行所选任务' }).click()
  await expect(page.getByText('succeeded')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('采样点：16471')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('img', { name: '总阵幅度图' })).toBeVisible()
  await expect(page.getByRole('img', { name: '总阵相位图' })).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载完整结果' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/task_evaluation_.*_result\.zip/)
})

test('rejects malformed JSON before creating an evaluation task', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('HFSS 工程绝对路径').fill(e2eProject)
  await page.getByRole('button', { name: '绑定工程' }).click()
  await expect(page.getByText('工程绑定成功，等待开始训练。')).toBeVisible()
  await page.getByLabel('固定 JSON 输入（JSON 是权威来源）').fill('{invalid json')
  await page.getByRole('button', { name: '执行所选任务' }).click()
  await expect(page.getByText('阵列输入必须是合法 JSON')).toBeVisible()
})

test('shows the backend duplicate-position validation error', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('HFSS 工程绝对路径').fill(e2eProject)
  await page.getByRole('button', { name: '绑定工程' }).click()
  await expect(page.getByText('工程绑定成功，等待开始训练。')).toBeVisible()
  await page.getByLabel('固定 JSON 输入（JSON 是权威来源）').fill(JSON.stringify({
    unit_count: 2,
    units: [
      { unit_id: 1, i: 1, j: 1, x: 0, y: 0 },
      { unit_id: 2, i: 1, j: 2, x: 0, y: 0 },
    ],
  }))
  await page.getByRole('button', { name: '执行所选任务' }).click()
  await expect(page.getByText('阵列中存在重复位置')).toBeVisible()
})
