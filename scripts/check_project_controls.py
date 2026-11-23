"""文件基本信息：scripts/check_project_controls.py

目的：在 CI 或本地检查项目索引、文件头、OpenAPI 和演示逻辑门禁。
输入：当前仓库文件。
输出：零退出码表示静态控制通过；否则打印问题并以非零退出。
维护：规则变化同步 AGENTS.md、验证规范和 scripts/目录索引.md。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "node_modules", "dist", ".pytest_cache", "__pycache__"}


def check_required_files(errors: list[str]) -> None:
    """检查关键索引、说明和基线文件；参数为错误列表，返回 None。"""

    required = [
        "AGENTS.md", "目录索引.md", "目录说明.md", "requirements.md", "architecture.md",
        "api.md", "openapi.yaml", "验证规范.md", "验收场景清单.md", "变更追踪矩阵.md",
        "backend/目录说明.md", "backend/目录索引.md", "frontend/目录说明.md", "frontend/目录索引.md",
        "tests/目录说明.md", "tests/目录索引.md", "scripts/目录说明.md", "scripts/目录索引.md",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required project file: {relative}")


def check_headers(errors: list[str]) -> None:
    """检查可维护文本/代码文件的基本信息头；参数为错误列表。"""

    extensions = {".py", ".md", ".yaml", ".yml", ".js", ".vue", ".css", ".html", ".toml"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name == "package-lock.json":
            continue  # npm 生成文件由 package.json 管理，不人工插入头部
        try:
            head = path.read_text(encoding="utf-8-sig")[:800]
        except UnicodeDecodeError:
            errors.append(f"not UTF-8 text: {path.relative_to(ROOT)}")
            continue
        if "文件基本信息" not in head:
            errors.append(f"missing file header: {path.relative_to(ROOT)}")
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8-sig"))
            except SyntaxError as exc:
                errors.append(f"python syntax error {path.relative_to(ROOT)}: {exc}")


def check_openapi(errors: list[str]) -> None:
    """检查 OpenAPI 八个规定 operation；参数为错误列表。"""

    try:
        import yaml
        document = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8-sig"))
    except Exception as exc:
        errors.append(f"openapi parse failed: {exc}")
        return
    expected = {
        ("/api/v1/projects", "get"), ("/api/v1/projects", "post"),
        ("/api/v1/projects/{project_id}", "get"),
        ("/api/v1/projects/{project_id}/training-tasks", "post"),
        ("/api/v1/projects/{project_id}/evaluation-tasks", "post"),
        ("/api/v1/tasks/{task_id}", "get"),
        ("/api/v1/tasks/{task_id}/results", "get"),
        ("/api/v1/tasks/{task_id}/download", "get"),
    }
    actual = {(path, method) for path, spec in document.get("paths", {}).items() for method in spec if method in {"get", "post"}}
    if actual != expected:
        errors.append(f"OpenAPI paths differ: expected {sorted(expected)}, got {sorted(actual)}")


def check_frontend_demo_removed(errors: list[str]) -> None:
    """检查正式 Vue 源码没有硬编码演示业务；参数为错误列表。"""

    source_dir = ROOT / "frontend" / "src"
    forbidden = {"FIXED_HFSS_PATH", "buildChartData", "resultRecords", "task_demo_", "setTimeout"}
    for path in source_dir.rglob("*"):
        if path.is_file() and path.suffix in {".vue", ".js"}:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    errors.append(f"demo token {token!r} remains in {path.relative_to(ROOT)}")


def main() -> int:
    """运行所有静态门禁；无参数，返回进程退出码。"""

    errors: list[str] = []
    check_required_files(errors)
    check_headers(errors)
    check_openapi(errors)
    check_frontend_demo_removed(errors)
    if errors:
        print("PROJECT CONTROLS FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PROJECT CONTROLS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
