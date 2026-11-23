> 文件基本信息：任务卡-TASK-BE-001.md  
> 用途：记录第一阶段后端契约骨架、状态编排、测试和证据。  
> 维护：任务继续推进或验收状态变化时同步变更追踪矩阵、目录索引和 Git commit。  

# TASK-BE-001：后端可运行契约骨架

| 项目 | 内容 |
|---|---|
| 类型 | 架构 + 实现 + 单元/集成/契约测试 |
| 关联基线 | FR-001、FR-002、FR-003、FR-005；BR-001、BR-003、BR-005、BR-012～BR-016；API-001～API-005；ADR-001～ADR-011；ALG-EQ-001 |
| 输入 | requirements.md、architecture.md、api.md、openapi.yaml、验证规范.md、验收场景清单.md、项目总览.md |
| 输出 | `backend/` 模块、SQLite schema、后台任务、HFSSAdapter/算法替身、结果下载、第一阶段测试 |
| 推荐模型 | 架构/状态审查：gpt-6.2-astra high；样板实现：gpt-6.2-sol medium；独立验证：gpt-6.2-sol high |
| 分支 | feature/development |
| Git 基线 | 1cf15d9 |

## 已完成

- 标准库 HTTP 服务和 8 个 API 路由骨架。
- `binding_status` 与 `model_status` 分离，避免 `ready_to_train` 冲突。
- SQLite 项目、任务和结果索引。
- 后台训练/评价任务和 prediction/validation 分支状态。
- JSON/网页输入规则的服务端校验、重复位置和字段校验。
- 开发 HFSSAdapter 和确定性算法替身，明确不代表真实 HFSS/最终算法通过。
- 结果目录、JSON 结果、元数据和 ZIP 下载。
- 9 个第一阶段单元/集成/契约测试，当前 `9 passed`。

## 待继续

- 真实后端算法适配和 `ALG-EQ-001` 黄金夹具。
- Vue 3 前端接入真实 `/api/v1`，移除 UI 原型演示逻辑。
- OpenAPI 运行时 schema 契约测试和 CI 工作流。
- 服务器 HFSS 人工验收：AC-001～AC-006、AC-020、AC-025～AC-027。

## 门禁状态

| 门禁 | 状态 |
|---|---|
| Python AST / TOML / OpenAPI YAML | passed |
| 本地 unit/integration/contract 测试 | passed：9 tests |
| 真实 HFSS 集成 | pending_external：服务器验收 |
| 关键算法等价性 | pending_external：黄金夹具待建立 |
| UI 真实 API E2E | pending：前端尚未实现 |

## 证据

```text
RUN-20261123-TASK-BE-001-local
命令：py -3.12 -m pytest -m "not hfss_server" -q
结果：9 passed in 0.37s
```
