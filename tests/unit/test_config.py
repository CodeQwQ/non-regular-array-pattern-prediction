"""文件基本信息：tests/unit/test_config.py

目的：验证正式服务配置默认为真实 HFSS/参考预测，测试入口必须显式选择 stub。
输入：隔离后的环境变量。
输出：pytest 配置测试证据。
维护：Settings 字段或部署默认值变化同步 backend/config.py、架构和部署文档。
"""

from backend.config import Settings


def test_server_defaults_to_real_modes(monkeypatch, tmp_path):
    """验证未设置测试替身变量时服务不会默认使用 stub。"""

    for name in (
        "ARRAYLAB_HFSS_MODE",
        "ARRAYLAB_PREDICTOR_MODE",
        "ARRAYLAB_HFSS_RUNNER_MODULE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ARRAYLAB_DB_PATH", str(tmp_path / "state.sqlite3"))
    monkeypatch.setenv("ARRAYLAB_DATA_ROOT", str(tmp_path / "data"))
    settings = Settings.from_env()
    assert settings.hfss_mode == "real"
    assert settings.predictor_mode == "reference"
    assert settings.hfss_design_name == "number1"
    assert settings.hfss_runner_module_path is None


def test_test_mode_is_explicit(monkeypatch, tmp_path):
    """验证测试进程可以显式启用两个 stub 模式。"""

    monkeypatch.setenv("ARRAYLAB_HFSS_MODE", "stub")
    monkeypatch.setenv("ARRAYLAB_PREDICTOR_MODE", "stub")
    monkeypatch.setenv("ARRAYLAB_DB_PATH", str(tmp_path / "state.sqlite3"))
    monkeypatch.setenv("ARRAYLAB_DATA_ROOT", str(tmp_path / "data"))
    settings = Settings.from_env()
    assert settings.hfss_mode == "stub"
    assert settings.predictor_mode == "stub"
