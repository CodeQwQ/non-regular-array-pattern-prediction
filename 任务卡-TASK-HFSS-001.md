> 文件基本信息：任务卡-TASK-HFSS-001.md  
> 用途：记录服务器 Windows 11 + HFSS 2021 人工验收和环境门禁。  
> 维护：工程文件、COM 版本、适配器或验收步骤变化时同步服务器测试、证据和追踪矩阵。  

# TASK-HFSS-001：服务器 HFSS 验收入口

| 项目 | 内容 |
|---|---|
| 关联基线 | NFR-001、NFR-004、NFR-006、AC-001～AC-006、AC-020、AC-025～AC-027 |
| 服务器命令 | `pytest -m hfss_server -q` |
| 必填环境 | `ARRAYLAB_HFSS_PROJECT_PATH`、Windows 11、HFSS 2021、win32com |
| 当前状态 | 验收入口已建立；开发机无合格工程，状态为 pending_external |

## 服务器验收要求

- 记录 RUN-ID、commit、Windows/HFSS/COM/许可证版本、工程文件和数据 hash。
- 先执行环境测试，再执行绑定、训练、验证、双模式、并发上限和资源释放场景。
- 失败必须保留日志、截图、任务状态、进程时间线和结果目录；不能以 stub 结果替代。
- 通过结论由服务器验收人员和审批人共同回填 `变更追踪矩阵.md`。
