"""文件基本信息：scripts/prepare_reference_data.py

目的：在真实模型训练前校验方向图、位置表、特征和 cn 数据，并生成 manifest。
输入：命令行指定的 CSV 文件和样本规模。
输出：JSON 数据 manifest，包含文件 hash、行数和字段信息。
维护：数据规则变化同步 data_io、黄金夹具、任务卡和交付说明。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from backend.data_io import load_cn_dataset, load_feature_csv, load_pattern_csv, load_position_table


def sha256_file(path: Path) -> str:
    """计算文件 SHA-256；参数为文件路径，返回十六进制 hash。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(args: argparse.Namespace) -> dict[str, object]:
    """读取并校验命令行数据，返回 manifest 字典。"""

    manifest: dict[str, object] = {"schema_version": "0.1", "files": {}, "checks": {}}
    pattern = Path(args.pattern)
    records = load_pattern_csv(pattern)
    manifest["files"]["pattern"] = {"path": str(pattern), "sha256": sha256_file(pattern), "rows": len(records)}
    manifest["checks"]["pattern_grid"] = "passed"
    if args.positions:
        position_path = Path(args.positions)
        positions = load_position_table(position_path, args.position_count)
        manifest["files"]["positions"] = {"path": str(position_path), "sha256": sha256_file(position_path), "rows": len(positions)}
        manifest["checks"]["positions"] = "passed"
    if args.features:
        feature_path = Path(args.features)
        features = load_feature_csv(feature_path, args.feature_rows)
        manifest["files"]["features"] = {"path": str(feature_path), "sha256": sha256_file(feature_path), "rows": len(features)}
        manifest["checks"]["features"] = "passed"
    if args.cn:
        cn_path = Path(args.cn)
        columns, rows = load_cn_dataset(cn_path, args.cn_samples)
        manifest["files"]["cn"] = {"path": str(cn_path), "sha256": sha256_file(cn_path), "rows": len(rows), "columns": columns}
        manifest["checks"]["cn_dataset"] = "passed"
    return manifest


def main() -> int:
    """解析参数、生成 manifest 并写盘；成功返回 0，数据不合格时由 loader 抛错。"""

    parser = argparse.ArgumentParser(description="Prepare and validate reference algorithm data")
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--positions")
    parser.add_argument("--position-count", type=int, default=25)
    parser.add_argument("--features")
    parser.add_argument("--feature-rows", type=int)
    parser.add_argument("--cn")
    parser.add_argument("--cn-samples", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = build_manifest(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
