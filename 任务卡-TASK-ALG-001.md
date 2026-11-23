> 文件基本信息：任务卡-TASK-ALG-001.md  
> 用途：记录关键业务算法纯函数提取、黄金夹具准备和等价性审查。  
> 维护：算法或黄金数据变化时同步项目总索引、变更追踪矩阵和 ALG-EQ-001 证据。  

# TASK-ALG-001：关键算法参考层

| 项目 | 内容 |
|---|---|
| 类型 | 算法适配 + 单元测试 + 黄金基线准备 |
| 关联基线 | ALG-EQ-001、requirements 领域数据约束、项目总览、AC-003～AC-005 |
| 输出 | `backend/algorithm_reference.py`、纯函数测试、3×3/5×5/25 阵元约束 |
| 推荐模型 | 算法实现/审查：gpt-6.2-astra high/xhigh；样板测试：gpt-6.2-sol low/medium |
| 当前状态 | 纯函数参考层已建立；黄金输入/输出和真实实验数据等价性待独立审查 |

## 已完成

- 训练规模 3×3/9、测试规模 5×5/25 和首单元原点约定。
- 八方位编号和 8 维最近邻距离倒数特征。
- 不显式构造巨大对角矩阵的 `build_zn` 等价公式。
- 91×181、16471 点方向图网格常量。
- 4 个算法单元测试，纳入本地 pytest。
- ECP 极化、虚拟阵元 flatten 顺序、正规方程 cn round-trip 和 6750 行展开规则已加入测试。

## 待完成

- 从真实实验数据生成 `manifest.json`、golden input/output 和 hash。
- 对 `Z@cn`、ECP 合成、相位对齐和误差指标执行独立等价性审查。
- 注入真实后端预测服务，替换 `StubPredictionEngine`。
- 服务器 HFSS 方向图数值对照。

## 当前证据

```text
命令：py -3.12 -m pytest -m "not hfss_server" -q
结果：17 passed
```
