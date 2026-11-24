> 文件基本信息：任务卡-TASK-DATA-002.md  
> 用途：记录真实实验数据进入模型训练前的 manifest 和 fail-loud 校验。  
> 维护：数据列、规模、hash 或黄金基线变化时同步 data_io、脚本和追踪矩阵。  

# TASK-DATA-002：真实数据准备 manifest

| 项目 | 内容 |
|---|---|
| 关联基线 | ALG-EQ-001、FR-001～FR-003、项目总览、数据约束 |
| 输出 | `scripts/prepare_reference_data.py`、manifest 单元测试 |
| 当前状态 | CLI 和测试已建立；真实数据文件尚未在当前工作区提供 |

## 使用示例

```powershell
py -3.12 scripts/prepare_reference_data.py `
  --pattern E:\\data\\Average_ECP_270.csv `
  --positions E:\\data\\antenna_position_data.csv `
  --features E:\\data\\train_features_iter_1.csv `
  --feature-rows 9 `
  --cn E:\\data\\dataset_single_element_6750.csv `
  --cn-samples 270 `
  --output artifacts/reference-data/manifest.json
```

真实文件缺失、字段错误、方向图网格错误、行数错误或 hash 不一致时，脚本必须失败。
