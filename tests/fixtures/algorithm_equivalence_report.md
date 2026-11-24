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
