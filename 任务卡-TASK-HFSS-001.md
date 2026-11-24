> 文件基本信息：任务卡-TASK-HFSS-001.md  
> 用途：记录服务器 Windows 11 + HFSS 2021 人工验收和环境门禁。  
> 维护：工程文件、COM 版本、适配器或验收步骤变化时同步服务器测试、证据和追踪矩阵。  

# TASK-HFSS-001：服务器 HFSS 验收入口

| 项目 | 内容 |
|---|---|
| 关联基线 | NFR-001、NFR-004、NFR-006、AC-001～AC-006、AC-020、AC-025～AC-027 |
| 服务器命令 | `pytest -m hfss_server -q` |
| 必填环境 | `ARRAYLAB_HFSS_PROJECT_PATH`、Windows 11、HFSS 2021、win32com |
| 当前状态 | 验收入口和 RealHFSSAdapter 延迟加载边界已建立；开发环境无工程，按用户决定暂跳过，后续人工验收 |

## 服务器验收要求

- 记录 RUN-ID、commit、Windows/HFSS/COM/许可证版本、工程文件和数据 hash。
- `ARRAYLAB_HFSS_MODE=real` 通过 RealHFSSAdapter 延迟加载实验 HFSS 类；训练/验证 runner 必须在服务器任务配置中注入。
- 验证 runner 成功返回时必须提供标准 `result`（`units` + `total_array`）；缺失结果由任务编排标记失败，不使用预测替身冒充真实验证。
- 先执行环境测试，再执行绑定、训练、验证、双模式、并发上限和资源释放场景。
- 失败必须保留日志、截图、任务状态、进程时间线和结果目录；不能以 stub 结果替代。
- 通过结论由服务器验收人员和审批人共同回填 `变更追踪矩阵.md`。

## 当前用户决策

开发环境只有 HFSS 程序，没有可用于测试的 `.aedt` 工程。当前跳过真实 HFSS 测试，不伪造通过；后续由用户在服务器/人工环境执行验收。
