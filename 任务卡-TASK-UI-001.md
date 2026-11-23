> 文件基本信息：任务卡-TASK-UI-001.md  
> 用途：记录 Vue 3/Vite 前端真实 API 接入和演示逻辑移除。  
> 维护：前端页面、API client 或 E2E 变化时同步目录索引、追踪矩阵和验收场景。  

# TASK-UI-001：Vue 真实 API 接入骨架

| 项目 | 内容 |
|---|---|
| 关联基线 | ADR-009、FR-001～FR-005、AC-009～AC-024、API-001～API-005 |
| 输出 | `frontend/` Vue 3/Vite 入口、API client、项目/任务/结果页面 |
| 当前状态 | 页面、真实 API client、生产构建和本地浏览器 E2E 已建立；服务器 HFSS E2E 待执行 |
| 关键约束 | 无硬编码项目、路径、任务、假数据、演示 Blob 和业务 setTimeout |

## 待完成

- 安装依赖并执行 `npm run build`。
- 执行 `npm run test:e2e`，验证真实 API 驱动的绑定、训练、评价、结果和下载流程。
- 连接本地 Python 后端完成 AC-009～AC-024 的浏览器 E2E。已覆盖绑定、训练、预测、结果和 ZIP 下载。
- 增加错误、部分成功和服务器 HFSS E2E 证据。
- 服务器或桌面壳环境确认本机 `.aedt` 路径选择方式。

## 当前证据

```text
目录：frontend/
命令：npm run build
结果：Vite 7.3.8 production build passed
命令：npm run test:e2e
结果：1 passed（Playwright 本地 stub 后端）
```
