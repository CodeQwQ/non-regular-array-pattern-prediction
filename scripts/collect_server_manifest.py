"""文件基本信息：scripts/collect_server_manifest.py

目的：生成服务器 HFSS 验收的可追踪 manifest，记录环境、commit、输入 hash 和证据路径。
输入：环境变量 ARRAYLAB_HFSS_PROJECT_PATH、可选模型/数据路径和 RUN_ID。
输出：artifacts/acceptance/<RUN-ID>/manifest.json。
维护：manifest 字段变化同步验证规范、验收场景清单和服务器验收记录。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str | None:
    """计算文件 SHA-256；参数为文件路径，不存在返回 None。"""

    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str | None:
    """读取当前 Git commit；不在仓库时返回 None。"""

    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_manifest(run_id: str | None = None) -> dict[str, object]:
    """构造服务器验收 manifest；参数为可选 RUN-ID，返回 JSON 字典。"""

    project_raw = os.getenv("ARRAYLAB_HFSS_PROJECT_PATH")
    if not project_raw:
        raise RuntimeError("ARRAYLAB_HFSS_PROJECT_PATH is required")
    project = Path(project_raw)
    if not project.is_absolute() or project.suffix.lower() != ".aedt" or not project.is_file():
        raise RuntimeError("ARRAYLAB_HFSS_PROJECT_PATH must be an accessible absolute .aedt file")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    resolved_run_id = run_id or os.getenv("ARRAYLAB_RUN_ID") or f"RUN-{stamp}-HFSS"
    optional_paths = {
        "project": project,
        "average_pattern": Path(os.environ["ARRAYLAB_AVERAGE_PATTERN_PATH"]) if os.getenv("ARRAYLAB_AVERAGE_PATTERN_PATH") else None,
        "model": Path(os.environ["ARRAYLAB_MODEL_PATH"]) if os.getenv("ARRAYLAB_MODEL_PATH") else None,
    }
    return {
        "run_id": resolved_run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "python": sys.version,
        "platform": platform.platform(),
        "windows_version": platform.version(),
        "hfss_version": os.getenv("ARRAYLAB_HFSS_VERSION"),
        "com_version": os.getenv("ARRAYLAB_COM_VERSION"),
        "license_info": os.getenv("ARRAYLAB_LICENSE_INFO"),
        "project": {key: {"path": str(path), "sha256": sha256_file(path)} for key, path in optional_paths.items() if path is not None},
        "data_root": os.getenv("ARRAYLAB_DATA_ROOT"),
        "hfss_module_path": os.getenv("ARRAYLAB_HFSS_MODULE_PATH"),
    }


def main() -> int:
    """生成 manifest 并打印路径；无参数，返回退出码。"""

    manifest = build_manifest()
    output_root = Path(os.getenv("ARRAYLAB_ACCEPTANCE_ROOT", "artifacts/acceptance")) / str(manifest["run_id"])
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / "manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
