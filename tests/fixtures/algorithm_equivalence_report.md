> 文件基本信息：tests/fixtures/algorithm_equivalence_report.md  
> 用途：记录 ALG-EQ-001 当前可在开发机复现的确定性纯函数黄金夹具验证结果及外部数据边界。  
> 维护：真实实验数据、模型或算法公式变化时，必须重新生成本报告并同步 manifest、算法黄金基线和追踪矩阵。  

# ALG-EQ-001 确定性算法等价性报告

## 本次范围

本报告只覆盖不依赖 HFSS、真实实验 CSV 或 XGBoost 产物的确定性规则：

- 3×3 中心单元的 8 维邻域特征顺序和数值；
- 小型 `Z` 矩阵的增益、相位和中心补偿公式；
- 纯函数单元测试中的 3×3/5×5 规模、虚拟阵列顺序、ECP 极化、cn round-trip、数据展开、方向图网格和总阵复场规则。

真实 270 组训练数据、25 组测试数据、Average ECP、XGBoost 模型和 HFSS 方向图没有进入当前工作区，因此本报告不宣称真实数据数值等价性或 HFSS 验收通过。

## 可复现命令

```powershell
py -3.12 -m pytest tests/unit/test_algorithm_reference.py tests/unit/test_golden_fixtures.py -q
```

预期结果：算法纯函数和确定性黄金夹具测试通过；任何字段、网格、顺序或数值变化都应使测试失败。

## 当前夹具哈希

| 文件 | SHA-256 |
|---|---|
| `manifest.json` | `57289fa3b08af7d1ea5f6101c39ddeaa91deadebbf08eced215069e1d3e685dd` |
| `golden_input/feature_center_3x3.json` | `e0cb2bb05f4e521cf1ad34c756159c5b02d75831bdb063ee3ee0ddbd934a34d1` |
| `golden_output/feature_center_3x3.json` | `5daa5e6a4f9fe7ff8a231cc3c348c295bf63c3bcc176a3fd136999a34b1836b3` |
| `golden_input/z_small.json` | `a77ca5a6a7949d562921cb7c8d81e262d188080ccf9991491304abc09cc4d29a` |
| `golden_output/z_small.json` | `4258719433f6f1c22af51e4e0318dedb7a5a30fd45746ad0cd1625dd8122cb7d` |

## 外部待办

拿到真实材料后，必须使用 `scripts/prepare_reference_data.py` 生成 reference manifest，并补充真实数据 hash、模型依赖版本、模型产物 hash、服务器 HFSS 对照结果和批准记录；在此之前 ALG-EQ-001 只能标记为“确定性夹具通过、真实数据 pending_external”。

## 实验脚本与后端 runner 对照审查

| 流程 | 原实验实现 | 当前后端实现 | 等价结论 |
|---|---|---|---|
| 3×3 布局 | `A_train_data_1.generate_5x5_antenna_array`，首点固定原点，其余点按 80 mil 格内随机生成 | `algorithm_reference.generate_grid_array`，首点和 80 mil/400 mil 格规则一致，使用 `1000 + iteration` 固定种子 | 公式和行列语义等价；随机序列由固定种子稳定化，真实数据仍需服务器对照 |
| 8 维特征 | `calculate_unit_features`，12/最近邻距离，八方位顺序固定 | `algorithm_reference.calculate_unit_features` | 黄金夹具已覆盖，等价 |
| HFSS 建模和导出 | `run_single_iteration`，移动、RelativeCS、底板、布尔、端口、求解、四类导出、`delete(5)` | `_simulate_training_iteration`，调用顺序和参数保持一致 | 已逐项对照；真实 COM 待验收 |
| ECP | `rEtheta*cos(phi-45)-rEphi*sin(phi-45)` | `polarized_ecp` | 公式和字段顺序等价 |
| 复数平均 | 270 组复数 ECP 求平均 | `average += ecp` 后除以 270 | 等价 |
| Z 矩阵 | `G @ E`，中心补偿 `-2`，25 虚拟阵元、27.5 GHz、0.005 m 间距 | `_build_z` 向量化实现 | 相位公式和虚拟阵元顺序等价，黄金 Z 夹具覆盖 |
| cn 求解 | `inv(ZᴴZ) @ Zᴴg` | `solve(ZᴴZ, Zᴴg)` | 数学解等价，数值实现更稳定；真实数据需记录浮点差异 |
| XGBoost | 9 列输入、2 列 cn、500/0.1/8/42 | `XGBoostCnModel` 使用相同参数 | 参数和列语义等价 |
| 预测 | 8 特征 + element_id 1～25，`Z @ cn`，ECP 幅相 | `ReferencePredictionEngine` | 预测链路和字段语义等价，黄金夹具覆盖纯算法 |
| 总阵 | 单元 ECP 按位置因子复数合成，幅值视图线性求和 | `synthesize_total_field` | 实验计划 011 口径等价 |
| 双模式误差 | 三切面 0/44/90°，θ≤90°，真实幅值峰值相位对齐 | `TaskManager._write_comparison` | 已补齐三切面、θ≤90°、峰值相位对齐和卷绕误差字段 |

### 有意保留的工程差异

HFSS 仿真不再由父进程共享 COM 对象。每个训练迭代和验证任务在 Windows `spawn` worker 中复制工程、创建独立 Desktop、写入隔离输出目录并在 worker 结束前调用 `close()`。这只改变进程和路径隔离方式，不改变训练数据字段、采样网格、公式或模型输入输出。

真实工程打开、求解、报告导出、进程计数和数值误差必须在服务器上回填。开发机的 spawn worker 测试只验证进程边界、迭代顺序、复制工程和清理行为，不能替代 COM 数值验收。
