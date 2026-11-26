"""文件基本信息：backend/logging_utils.py

目的：配置项目级磁盘日志，使致命错误与项目/任务标识可被服务器排查。
输入：项目数据根目录。
输出：配置好的 `arraylab` logger 和统一格式的日志文件。
维护：日志路径、保留策略或字段变化同步架构、需求、验证规范、目录索引和测试。
"""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(data_root: str | Path) -> logging.Logger:
    """配置项目日志文件；参数为数据根目录，返回可写的项目 logger。"""

    root = Path(data_root)
    root.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("arraylab")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = logging.FileHandler(root / "arraylab.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger
