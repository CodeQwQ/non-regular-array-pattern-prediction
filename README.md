> 文件基本信息：README.md  
> 用途：远端仓库入口，说明项目范围、当前交付状态和部署文档位置。  
> 维护：启动命令、分支、门禁或发布状态变化时同步基线文档、验证规范、验收清单和根目录索引。  

# 非规则阵列方向图预测工具

这是一个按需求、架构、接口、UI 和验证规范重构的 HFSS 非规则阵列方向图预测工具，包含 Python 后端、Vue 3 工作台、算法参考层、测试门禁和服务器 HFSS 验收入口。

Windows/HFSS 服务器的 Python 依赖清单见 [`requirements-server.txt`](requirements-server.txt)。离线部署时先在联网机器按该清单下载对应 Python 3.12 wheel，再复制到服务器安装。

## 当前状态

当前 `feature/development` 可作为开发合并版本使用。项目控制、Python 测试、算法确定性夹具、前端构建和 Playwright E2E 已建立；正式发布仍需要真实实验数据、模型产物和服务器 HFSS 人工验收。

## 快速启动

详细的 Windows 服务器部署、依赖安装、环境变量、后端/前端启动和 HFSS 验收步骤见：

- [`验证规范.md`](验证规范.md)
- [`验收场景清单.md`](验收场景清单.md)

后端从仓库根目录启动：

```powershell
python -m backend.server
```

前端另开终端启动：

```powershell
cd frontend
npm ci
npm run dev
```

默认访问地址：`http://127.0.0.1:5173`；后端健康检查：`http://127.0.0.1:8000/health`。

正式服务默认使用真实 HFSS 和参考预测模式。网页绑定时填写 `.aedt` 工程绝对路径，设计名默认 `number1`，点击开始训练后由仓库内 runner 自动生成训练数据并训练模型。开发机测试必须显式设置两个 `stub` 模式变量。

## Windows 服务器部署

1. 将仓库完整复制到服务器，并确认 HFSS 2021、Python 3.12、Node.js/npm 已安装，HFSS 许可证可用。
2. 在联网机器按 `requirements-server.txt` 下载 Windows/Python 3.12 wheel，复制到服务器的离线目录后安装。

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --find-links E:\wheelhouse -r requirements-server.txt
```

3. 启动后端。首次真实运行不需要设置工程路径、模型路径、平均 ECP 路径或 `hfss.py` 路径。

```powershell
$env:ARRAYLAB_DATA_ROOT = "E:\ArrayLab\data"
$env:ARRAYLAB_CLEANUP_ENABLED = "1"
.venv\Scripts\python.exe -m backend.server
```

4. 另开终端安装并启动前端。服务器离线时需要提前准备 npm 缓存，或直接复制已安装的 `frontend/node_modules`。

```powershell
cd frontend
npm ci --offline
npm run dev -- --host 127.0.0.1
```

5. 浏览器打开 `http://127.0.0.1:5173`，填写 `.aedt` 绝对路径并点击绑定。工程路径由网页传给后端，设计名默认为 `number1`。绑定成功后点击开始训练，训练数据、HFSS 导出、ECP/cn 后处理和模型训练由默认 runner 自动执行。

`ARRAYLAB_HFSS_PROJECT_PATH` 只供服务器验收 manifest 脚本使用，不是正常网页运行的必填项。`ARRAYLAB_HFSS_MODULE_PATH`、`ARRAYLAB_HFSS_RUNNER_MODULE_PATH`、`ARRAYLAB_AVERAGE_PATTERN_PATH` 和 `ARRAYLAB_MODEL_PATH` 也有仓库内默认行为，只有替换实现或预置模型时才配置。

## 开发门禁

```powershell
python scripts/check_project_controls.py
python -m pytest -m "not hfss_server" -q
cd frontend
npm run build
npm run test:e2e
```

真实 HFSS 测试必须在 Windows/HFSS 服务器上执行，开发机不得用 stub 结果替代真实验收。
