> 文件基本信息：任务卡-TASK-CI-001.md  
> 用途：记录项目控制脚本、CI 工作流和本地质量门禁。  
> 维护：门禁命令或目录变化时同步 AGENTS.md、验证规范、目录索引和 CI 配置。  

# TASK-CI-001：自动化项目质量门禁

| 项目 | 内容 |
|---|---|
| 关联基线 | AGENTS.md、验证规范第 7/10 节、DOC-INDEX-001、API、UI |
| 输出 | `scripts/check_project_controls.py`、`.github/workflows/quality.yml` |
| 当前状态 | 本地项目控制、39 个 Python 测试和 Vite 构建均通过；HFSS 服务器门禁仍外置 |

## 当前命令

```text
py -3.12 scripts/check_project_controls.py
py -3.12 -m pytest -m "not hfss_server" -q
cd frontend && npm ci && npm run build
```

## 边界

- CI 检查文件头、索引存在性、OpenAPI 八个端点和 Vue 演示逻辑移除。
- CI 不伪造真实 HFSS、COM、模型质量或服务器方向图等价性。
- `pending_external` 的 HFSS 用例必须在服务器验收后回填追踪矩阵。
