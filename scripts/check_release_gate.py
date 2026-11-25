"""文件基本信息：scripts/check_release_gate.py

目的：阻止 stub、缺少真实数据或未完成 HFSS 验收的状态被标记为可发布。
输入：环境变量 ARRAYLAB_PREDICTOR_MODE、ARRAYLAB_REFERENCE_MANIFEST、ARRAYLAB_HFSS_RUN_MANIFEST、ARRAYLAB_HFSS_ACCEPTANCE_STATUS。
输出：发布门禁检查结果；不满足时非零退出。
维护：发布条件变化同步验证规范、验收场景清单和追踪矩阵。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def load_json(path: str | None, label: str) -> dict[str, object]:
    """读取并返回 manifest；参数为路径和标签，缺失/无效时抛出 RuntimeError。"""

    if not path:
        raise RuntimeError(f"{label} is required")
    file_path = Path(path)
    if not file_path.is_file():
        raise RuntimeError(f"{label} file does not exist: {file_path}")
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain an object")
    return value


def check_release_gate() -> dict[str, object]:
    """检查 reference 模式、数据 manifest 和服务器 HFSS 状态，返回门禁报告。"""

    if os.getenv("ARRAYLAB_PREDICTOR_MODE", "stub").lower() != "reference":
        raise RuntimeError("ARRAYLAB_PREDICTOR_MODE must be reference for release")
    reference = load_json(os.getenv("ARRAYLAB_REFERENCE_MANIFEST"), "ARRAYLAB_REFERENCE_MANIFEST")
    hfss = load_json(os.getenv("ARRAYLAB_HFSS_RUN_MANIFEST"), "ARRAYLAB_HFSS_RUN_MANIFEST")
    if os.getenv("ARRAYLAB_HFSS_ACCEPTANCE_STATUS", "").lower() != "passed":
        raise RuntimeError("ARRAYLAB_HFSS_ACCEPTANCE_STATUS must be passed for release")
    if reference.get("real_hfss_data") is False:
        raise RuntimeError("reference manifest still declares real_hfss_data=false")
    if hfss.get("acceptance_status") != "passed":
        raise RuntimeError("HFSS manifest acceptance_status must be passed")
    return {"status": "passed", "reference_manifest": reference, "hfss_manifest": hfss}


def main() -> int:
    """执行发布门禁并打印结果；成功返回 0，失败返回 1。"""

    try:
        report = check_release_gate()
    except RuntimeError as exc:
        print(f"RELEASE GATE FAILED: {exc}")
        return 1
    print(json.dumps({"status": report["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
