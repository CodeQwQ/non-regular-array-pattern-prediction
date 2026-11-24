> 文件基本信息：任务卡-TASK-RELEASE-001.md  
> 用途：记录发布门禁，阻止 stub 或缺少真实验收证据的版本发布。  
> 维护：发布条件变化时同步验证规范、交付说明、脚本和追踪矩阵。  

# TASK-RELEASE-001：真实交付发布门禁

| 项目 | 内容 |
|---|---|
| 关联基线 | 验证规范开发/发布门禁、ALG-EQ-001、TASK-HFSS-001、TASK-DATA-002 |
| 脚本 | `py -3.12 scripts/check_release_gate.py` |
| 当前状态 | 门禁逻辑和测试已建立；真实 reference/HFSS manifest 尚未提供 |

## 通过条件

- `ARRAYLAB_PREDICTOR_MODE=reference`；
- reference manifest 存在且 `real_hfss_data=true`；
- HFSS manifest 存在且 `acceptance_status=passed`；
- `ARRAYLAB_HFSS_ACCEPTANCE_STATUS=passed`。

开发测试仍可以使用 stub，但不能通过该发布门禁。
