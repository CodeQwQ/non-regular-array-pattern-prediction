> 文件基本信息：tests/fixtures/HFSSAdapter契约.md  
> 用途：规定 HFSSAdapter 测试替身与真实 COM 适配层之间的最小契约。  
> 维护：新增接口、输出字段或异常分类时同步 API、架构、测试和服务器验收记录。  

# HFSSAdapter 测试替身契约

## 输入

- 工程绝对路径、设计名和项目标识；
- 阵列规模、单元位置、报告前缀和坐标系；
- 训练/验证任务编号、取消和超时控制。

## 输出

- 阶段状态：queued、running、succeeded、failed；
- 进程信息和并发计数；
- 方向图字段 `Phi[deg]`、`Theta[deg]`、`ECP_dB`、`ECP_Phase_deg`；
- Theta/Phi 网格、单位、采样点数、输出文件和任务关联信息。

训练 runner 成功时还必须在返回字典的 `model_path` 字段提供可访问的模型产物路径；真实 runner 缺少该字段或文件不可访问时，任务必须失败并保持模型不可用。开发 stub 可以省略该字段，但 stub 结果不构成真实训练证据。

验证 runner 成功时还必须在返回字典的 `result` 字段提供标准结果对象：

```json
{
  "implementation": "hfss_com",
  "units": {"1": [{"Phi[deg]": 0, "Theta[deg]": 0, "ECP_dB": 0, "ECP_Phase_deg": 0}]},
  "total_array": {"records": [{"Phi[deg]": 0, "Theta[deg]": 0, "ECP_dB": 0, "ECP_Phase_deg": 0}]}
}
```

真实适配器没有 `result` 时必须进入失败状态；开发 stub 可以由预测替身补齐结果，但这不构成真实 HFSS 验收证据。

## 必须可注入的失败

工程路径无效、HFSS 启动失败、COM 调用失败、超时、异常退出、并发资源不足、导出缺列/缺行、写盘失败、取消和残留进程。

测试替身通过不代表真实 HFSS 通过。真实工程加载、COM 调用、方向图数值和资源回收必须在服务器人工验收中确认。
