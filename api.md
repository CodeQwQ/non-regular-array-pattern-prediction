> 文件基本信息：api.md  
> 用途：接口说明，定义 HTTP 请求、响应、状态、错误和任务行为。  
> 维护：修改后同步目录索引、追踪矩阵和相关测试。  

# 非规则阵列方向图预测工具 API 文档

## 1. 文档信息与范围

| 项目 | 内容 |
|---|---|
| 文档状态 | 已确认，OpenAPI 初稿已生成，待实现验证 |
| 文档版本 | v0.5 |
| API 版本 | `/api/v1` |
| 关联文档 | `requirements.md`、`architecture.md` |
| 最近更新日期 | 2026-11-23 |
| 本次更新 | 明确 JSON 优先、前端简单校验与后端权威校验、真实 runner 产物契约，并保留绑定与手动训练分步执行 |

本文档定义前端与后端之间的业务接口契约，覆盖工程绑定、训练任务、预测/验证任务、状态查询、结果查询和结果下载。机器可读契约见同目录下的 `openapi.yaml`。

本文档不描述：

- 具体算法实现；
- HFSS 内部调用过程；
- SQLite 表结构；
- 前端页面布局；
- 详细磁盘目录规则。

## 2. API 通用约定

### 2.1 基础约定

- 通信方式：HTTP。
- 数据格式：JSON。
- 字符编码：UTF-8。
- 长任务采用异步执行，接口返回 `task_id`。
- 前端通过任务状态接口轮询。
- 项目和任务使用唯一 ID。
- 时间格式：`YYYY-MM-DD HH:mm:ss`。

### 2.2 成功状态码

| 状态码 | 用途 |
|---|---|
| 200 | 查询或下载成功 |
| 201 | 创建项目或任务成功 |
| 202 | 请求已接受并进入后台执行 |

### 2.3 常用错误状态码

| 状态码 | 用途 |
|---|---|
| 400 | 请求格式或参数错误 |
| 404 | 项目、任务或结果不存在 |
| 409 | 当前状态不允许执行 |
| 500 | 系统内部错误 |

## 3. 资源与状态表示

### 3.1 项目

```json
{
  "project_id": "project_001",
  "project_name": "a",
  "hfss_project_name": "a",
  "model_status": "ready",
  "created_at": "2026-11-19 10:00:00",
  "updated_at": "2026-11-19 10:30:00"
}
```

`model_status`：

```text
unbound
training
ready
failed
invalid
```

### 3.2 任务

```json
{
  "task_id": "task_001",
  "project_id": "project_001",
  "task_type": "training",
  "status": "running",
  "current_stage": "hfss_simulation",
  "created_at": "2026-11-19 10:00:00",
  "updated_at": "2026-11-19 10:05:00",
  "result_available": false,
  "error": null
}
```

主任务状态：

```text
queued
running
succeeded
partial_success
failed
validation_failed
```

### 3.3 预测和验证分支

```json
{
  "prediction_status": "succeeded",
  "validation_status": "running"
}
```

分支状态：

```text
not_selected
queued
running
succeeded
failed
```

## 4. 接口目录与详细定义

### 4.1 绑定 HFSS 工程并创建项目

```http
POST /api/v1/projects
Content-Type: application/json
```

请求示例：

```json
{
  "hfss_project_path": "E:\\projects\\a.aedt"
}
```

职责：

- 用户点击选择工程，通过资源管理器选择 HFSS 工程文件；
- 前端向后端提交工程文件的本机绝对路径；
- 系统校验路径和工程文件是否可访问；
- 系统按该路径启动 HFSS 并绑定工程；
- 系统不上传、不复制 HFSS 工程文件；
- 创建项目并将项目置为“已绑定 / 待训练”；
- 本接口不自动启动训练，训练由用户随后点击“开始训练”触发。

第一版只接受 HFSS 工程文件路径，不接受压缩包或普通文件。

返回示例：

```json
{
  "project_id": "project_001",
  "status": "ready_to_train"
}
```

### 4.2 获取项目列表

```http
GET /api/v1/projects
```

职责：

- 返回当前可展示在前端项目列表中的项目；
- 返回项目绑定状态和模型状态；
- 按最近更新时间倒序返回，具体排序由后端统一实现。

返回示例：

```json
{
  "items": [
    {
      "project_id": "project_001",
      "project_name": "a",
      "hfss_project_name": "a",
      "model_status": "ready",
      "created_at": "2026-11-19 10:00:00",
      "updated_at": "2026-11-19 10:30:00"
    }
  ]
}
```

### 4.3 查询项目和模型状态

```http
GET /api/v1/projects/{project_id}
```

职责：

- 查询项目是否绑定；
- 查询模型是否正在训练；
- 查询模型是否可以用于预测；
- 返回项目基础信息。

### 4.4 开始训练

```http
POST /api/v1/projects/{project_id}/training-tasks
Content-Type: application/json
```

职责：

- 校验项目已经成功绑定 HFSS 工程且当前允许训练；
- 创建后台训练任务；
- 训练流程依次生成训练数据、执行小阵列 HFSS 仿真、提取数据并训练模型；
- 训练成功的内部 runner 必须返回可访问的模型产物，参考预测模式还必须提供平均 ECP 产物。仓库内默认 runner 会自动生成 3×3 训练数据、完成 ECP/cn 后处理和 XGBoost 训练。后端在加载二者前不会把项目标记为 `ready`，缺少产物时任务进入失败状态；不得用 stub 结果替代真实训练。
- 返回训练任务编号，前端通过任务状态接口观察进度。

本接口由用户点击“开始训练”触发。训练失败后，用户可在处理原因后再次创建训练任务。

返回示例：

```json
{
  "task_id": "task_training_001",
  "project_id": "project_001",
  "status": "queued"
}
```

### 4.5 创建预测/验证任务

```http
POST /api/v1/projects/{project_id}/evaluation-tasks
Content-Type: application/json
```

职责：

- 接收阵列输入；
- 校验输入格式、必填项、数量、位置和解析结果；
- 校验模型状态；
- 校验预测/验证模式；
- 选择 prediction 时要求项目已有可用模型；
- 选择 validation 时要求已绑定且可调用的 HFSS 环境；
- 创建后台任务。

JSON 与页面输入统一由后端解析和校验；文件内容与页面选择之间的关系由后端按接口规则判定，前端不替代后端作最终判断。

请求示例：

```json
{
  "input": {
    "unit_count": 3,
    "units": [
      {"unit_id": 1, "i": 1, "j": 1, "x": 0.0, "y": 0.0},
      {"unit_id": 2, "i": 1, "j": 2, "x": 10.0, "y": 0.0},
      {"unit_id": 3, "i": 2, "j": 1, "x": 0.0, "y": 10.0}
    ]
  },
  "modes": ["prediction", "validation"]
}
```

`modes` 至少包含一个值：

```text
prediction
validation
```

返回示例：

```json
{
  "task_id": "task_eval_001",
  "project_id": "project_001",
  "status": "queued"
}
```

### 4.6 查询任务状态

```http
GET /api/v1/tasks/{task_id}
```

职责：

- 查询主任务状态；
- 查询当前阶段；
- 查询预测分支状态；
- 查询验证分支状态；
- 返回提示信息和错误信息；
- 返回结果是否可用。

返回示例：

```json
{
  "task_id": "task_eval_001",
  "task_type": "evaluation",
  "status": "running",
  "current_stage": "validation",
  "prediction_status": "succeeded",
  "validation_status": "running",
  "result_available": false,
  "message": "正在执行 HFSS 验证",
  "error": null
}
```

### 4.7 获取任务结果

```http
GET /api/v1/tasks/{task_id}/results
```

职责：

- 获取页面展示所需的结果；
- 返回总阵方向图；
- 返回幅度和相位数据；
- 双模式成功时返回预测线和验证线；
- 返回结果文件信息。

页面只展示总阵结果，子单元结果保存在完整任务结果中。

结果内部数据格式沿用现有实验代码的输出格式，API 只增加统一的外层结构。

### 4.8 下载任务结果

```http
GET /api/v1/tasks/{task_id}/download
```

职责：

- 下载一个任务的完整结果包；
- 包含子单元结果；
- 包含总阵结果；
- 包含预测、验证和对比数据；
- 包含必要的输入和任务元数据。

第一版不提供按结果类型分别下载的接口。

## 5. 请求与响应数据模型

### 5.1 阵列输入

固定包含：

```text
unit_count
units
unit_id
i
j
x
y
```

约束沿用需求文档：

- `unit_count` 等于 `units` 长度；
- `unit_id` 从 1 到 n 连续；
- 对外 `i、j` 从 1 开始；
- 内部转换为算法所需索引；
- `x、y` 单位为 mil；
- 位置不能重复。
- JSON 文件与网页输入同时存在时，以 JSON 文件为准；前端可以做必填、类型等简单校验，后端必须执行复杂校验、规范化和最终判定。
- 后端不得接受前端校验通过作为业务合法性的唯一依据；`unit_count`、数组顺序、`unit_id`、`i/j`、坐标数值和位置唯一性必须在服务端再次校验。

### 5.2 方向图数据记录

现有实验代码生成的单元 ECP 和总阵 ECP 均使用以下 4 列：

```json
{
  "Phi[deg]": 0.0,
  "Theta[deg]": 0.0,
  "ECP_dB": -12.345678,
  "ECP_Phase_deg": 45.678901
}
```

- 每个方向图通常包含 16471 个采样点；
- 网格为 Theta 0°～180°、Phi 0°～360°，步长均为 2°；
- 单元预测结果、单元验证结果、总阵预测结果和总阵验证结果均沿用这 4 列；
- API 不改变现有实验代码的字段名称和数值语义。

### 5.3 结果响应外层结构

```json
{
  "task_id": "task_eval_001",
  "status": "succeeded",
  "mode": "comparison",
  "total_array_result": {
    "prediction": {"records": []},
    "validation": {"records": []}
  },
  "files": [
    {
      "name": "total_array_ecp_pred.csv",
      "type": "total_array_data",
      "source": "prediction",
      "downloadable": true
    },
    {
      "name": "total_array_ecp_real.csv",
      "type": "total_array_data",
      "source": "validation",
      "downloadable": true
    },
    {
      "name": "total_array_ecp_compare.png",
      "type": "comparison_plot",
      "source": "comparison",
      "downloadable": true
    }
  ]
}
```

单模式时只返回已执行分支；双模式时返回预测和验证两组总阵记录。

### 5.4 实验结果文件字段

| 文件类型 | 字段 |
|---|---|
| 单元/总阵方向图 | `Phi[deg]`、`Theta[deg]`、`ECP_dB`、`ECP_Phase_deg` |
| 相位对齐数据 | `sample_id`、`cut_phi_deg`、`align_theta_deg`、`phase_offset_deg` |
| 总阵误差汇总 | `cut_phi_deg`、`amp_rmse_dB`、`amp_mae_dB`、`corr_amp`、`phase_rmse_deg`、`phase_mae_deg`、`rel_l2`、`align_theta_deg`、`phase_offset_deg` |
| 单样本误差明细 | `sample_id`、`cut_phi_deg`、`cn_rel_l2`、`cn_max_abs_err`、`amp_mean_err_dB`、`amp_max_err_dB`、`phase_mean_err_deg`、`phase_mean_err_aligned_deg`、`rel_l2`、`corr_amp` |
| 误差总体汇总 | `layer`、`scope`、`metric`、`mean`、`max`、`min` |
| cn 数据 | `sample_id`、`element_id`、`cn_real`、`cn_imag` |

### 5.5 错误响应

统一采用：

```json
{
  "error": {
    "code": "INPUT_INVALID",
    "message": "阵列输入校验失败",
    "details": [
      {
        "field": "units",
        "reason": "存在重复位置"
      }
    ]
  }
}
```

初步错误编码：

```text
PROJECT_PATH_INVALID
PROJECT_BIND_FAILED
INPUT_INVALID
MODE_REQUIRED
MODEL_NOT_READY
DUPLICATE_POSITION
TASK_FAILED
RESULT_NOT_READY
DOWNLOAD_FAILED
INTERNAL_ERROR
```

## 6. 异步任务、状态与错误约定

### 6.1 任务创建

任务创建接口只负责：

1. 接收请求；
2. 同步校验；
3. 创建任务；
4. 返回 `task_id`。

训练、预测和验证在后台执行。

### 6.2 前端轮询

前端通过以下接口轮询：

```http
GET /api/v1/tasks/{task_id}
```

任务处于以下状态时继续轮询：

```text
queued
running
```

任务处于以下状态时停止轮询：

```text
succeeded
partial_success
failed
validation_failed
```

### 6.3 双模式结果

| 预测分支 | 验证分支 | 主任务结果 |
|---|---|---|
| 成功 | 未选择 | 预测结果 |
| 未选择 | 成功 | 验证结果 |
| 成功 | 成功 | 预测与验证对比结果 |
| 成功 | 失败 | 保留预测结果 |
| 失败 | 成功 | 保留验证结果 |
| 失败 | 失败 | 任务失败 |

## 7. 结果与文件操作

- 页面查询总阵结果；
- 结果中包含幅度和相位；
- 双模式包含两条曲线；
- 完整子单元结果、总阵结果、对比图和误差数据通过任务结果包下载；
- 下载接口返回一个完整任务压缩包；
- 结果文件内容沿用现有实验代码字段，实际目录仍按需求文档规定保存；
- API 不直接暴露内部目录结构。

## 8. 版本与需求追溯

- API 使用 `/api/v1`；
- 破坏性接口变化升级主版本；
- 新增字段尽量保持向后兼容；
- 接口与需求编号建立关联；
- 工程绑定与训练启动分开；训练由用户点击“开始训练”接口启动，训练失败后可重新创建训练任务。

| API | 主要关联需求 |
|---|---|
| 绑定 HFSS 工程并创建项目 | FR-001、BR-003 |
| 获取项目列表 | 页面项目列表展示 |
| 开始训练 | FR-001、BR-004 |
| 创建预测/验证任务 | FR-002、FR-005 |
| 查询任务状态 | NFR-002、NFR-005 |
| 获取结果 | FR-003 |
| 下载结果 | FR-003、BR-010 |
| 错误响应 | NFR-003、状态与异常处理 |

## 已确认的接口决策

| 编号 | 决策 |
|---|---|
| API-001 | 用户通过网页资源管理器选择 HFSS 工程文件，API 接收本机绝对路径；系统按路径启动 HFSS，不上传或复制工程文件 |
| API-002 | 一个任务使用一个完整结果包下载 |
| API-003 | 结果内部数据格式沿用现有实验代码，仅增加统一外层结构 |
| API-004 | 工程绑定不自动训练；用户通过开始训练接口显式创建训练任务，失败后可重试 |
| API-005 | JSON 与网页输入同时存在时 JSON 优先；前端负责简单校验，后端负责复杂校验、规范化和最终判定 |

