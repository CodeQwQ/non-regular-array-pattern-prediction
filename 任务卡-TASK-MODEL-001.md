> 文件基本信息：任务卡-TASK-MODEL-001.md  
> 用途：记录 XGBoost cn 模型适配、输入列校验和模型产物边界。  
> 维护：模型参数、依赖版本或产物格式变化时同步模型适配器、黄金基线和追踪矩阵。  

# TASK-MODEL-001：XGBoost cn 模型适配器

| 项目 | 内容 |
|---|---|
| 关联基线 | 项目总览 XGBoost 参数、ALG-EQ-001、FR-001、AC-005/AC-014 |
| 输出 | `backend/model_adapter.py`、模型输入/状态单元测试 |
| 当前状态 | 适配器接口和 24 个本地测试已完成；真实 xgboost 训练和模型 hash 待算法环境执行 |
| 参数 | `n_estimators=500`、`learning_rate=0.1`、`max_depth=8`、`random_state=42` |

## 约束

- 输入固定为 9 列：8 维布局特征 + `element_id`。
- 输出固定为 2 列：`cn_real`、`cn_imag`。
- 未安装 xgboost 时返回明确依赖错误，不伪造训练成功。
- 旧脚本的 `skiprows=26` 不进入适配器；数据读取由 `data_io.py` 严格校验。

## 待完成

- 在具备 xgboost 和真实训练数据的环境中训练模型。
- 保存模型产物、依赖版本、随机种子和数据 hash。
- 接入 `TaskManager` 的真实训练/预测分支并完成黄金等价性审查。
