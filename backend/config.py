"""文件基本信息：backend/config.py

目的：集中管理服务监听、SQLite、结果目录和适配器模式配置。
输入：环境变量。
输出：Settings 配置对象和目录创建结果。
维护：修改后同步 backend/目录索引.md、测试和 API/架构文档。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """后端运行配置。"""

    host: str
    port: int
    db_path: Path
    data_root: Path
    hfss_mode: str = "stub"
    max_hfss_workers: int = 4
    predictor_mode: str = "stub"
    average_pattern_path: Path | None = None
    model_path: Path | None = None
    cleanup_enabled: bool = False
    retention_days: int = 90

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量读取配置。

        参数：无。
        返回：根据当前环境变量构造的 Settings。
        """

        project_root = Path(__file__).resolve().parents[1]
        default_data = project_root.parent / "data"
        return cls(
            host=os.getenv("ARRAYLAB_HOST", "127.0.0.1"),
            port=int(os.getenv("ARRAYLAB_PORT", "8000")),
            db_path=Path(os.getenv("ARRAYLAB_DB_PATH", str(project_root / "arraylab.sqlite3"))),
            data_root=Path(os.getenv("ARRAYLAB_DATA_ROOT", str(default_data))),
            hfss_mode=os.getenv("ARRAYLAB_HFSS_MODE", "stub").lower(),
            predictor_mode=os.getenv("ARRAYLAB_PREDICTOR_MODE", "stub").lower(),
            average_pattern_path=Path(os.environ["ARRAYLAB_AVERAGE_PATTERN_PATH"]) if os.getenv("ARRAYLAB_AVERAGE_PATTERN_PATH") else None,
            model_path=Path(os.environ["ARRAYLAB_MODEL_PATH"]) if os.getenv("ARRAYLAB_MODEL_PATH") else None,
            cleanup_enabled=os.getenv("ARRAYLAB_CLEANUP_ENABLED", "0") == "1",
            retention_days=int(os.getenv("ARRAYLAB_RETENTION_DAYS", "90")),
            max_hfss_workers=min(4, max(1, int(os.getenv("ARRAYLAB_HFSS_WORKERS", "4")))),
        )

    def ensure_directories(self) -> None:
        """创建 SQLite 父目录和数据根目录。

        参数：无。
        返回：无；目录创建失败时抛出 OSError。
        """

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
