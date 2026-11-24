> 文件基本信息：任务卡-TASK-DATA-001.md  
> 用途：记录实验 CSV/方向图/位置表/cn 数据适配和 fail-loud 校验。  
> 维护：数据格式或黄金夹具变化时同步 backend/data_io.py、测试、追踪矩阵和索引。  

# TASK-DATA-001：实验数据边界适配

| 项目 | 内容 |
|---|---|
| 关联基线 | FR-001～FR-003、BR-005～BR-010、ALG-EQ-001、AC-003～AC-016 |
| 输出 | `backend/data_io.py`、方向图/位置/特征/cn CSV fail-loud 测试 |
| 当前状态 | 纯文件边界测试已完成并纳入全套 44 个本地测试；真实数据 hash 和服务器样本待建立 |

## 已完成

- 方向图字段、点数、角度网格、重复键、NaN/Inf 校验。
- 位置表 `unit_id` 连续性和 mil→m 转换。
- 8 维特征字段顺序和 cn 11 列展开数据检查。
- 禁止 `skiprows=26` 导致首个 25 行样本丢失。

## 待完成

- 接入真实 270 组训练数据和 25 组测试数据。
- 生成黄金数据 manifest、hash 和等价性报告。
- 将 CSV 适配器接入真实预测/训练任务，替换开发替身。

## 当前证据

```text
命令：py -3.12 -m pytest -m "not hfss_server" -q
结果：44 passed, 1 deselected
```
