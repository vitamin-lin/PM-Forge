#!/usr/bin/env python3
"""Create or locate a stable PM Forge requirement record in a project."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


CONFIG_NAME = "pm-forge.json"
RECORD_NAME = "需求档案.json"
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}


def artifact_root(project: Path) -> Path:
    config_path = project / CONFIG_NAME
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError(f"{CONFIG_NAME} 必须是 JSON 对象")
        relative = config.get("artifact_root", ".")
    else:
        relative = "."  # 兼容既有项目的 [需求名]/ 目录
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError("artifact_root 必须是非空的项目内相对路径")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("artifact_root 必须位于项目目录内")
    root = (project / raw).resolve()
    if not root.is_relative_to(project):
        raise ValueError("artifact_root 解析后超出项目目录")
    return root


def requirement_name(value: str) -> str:
    name = value.strip()
    if (not name or name in {".", ".."} or name.endswith((" ", "."))
            or INVALID_NAME.search(name) or name.upper().split(".", 1)[0] in WINDOWS_RESERVED):
        raise ValueError("需求名不能包含路径字符、控制字符或系统保留名称")
    return name


def initialize(project: Path, name: str) -> Path:
    project = project.resolve()
    if not project.is_dir():
        raise ValueError(f"项目目录不存在：{project}")
    name = requirement_name(name)
    root = artifact_root(project)
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError("需求目录超出产物目录")
    record = target / RECORD_NAME
    if record.is_file():
        existing = json.loads(record.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or not existing.get("requirement_id"):
            raise ValueError(f"已有需求档案缺少 requirement_id：{record}")
        return record
    target.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc)
    now = created.isoformat(timespec="seconds")
    payload = {
        "schema_version": 1,
        "requirement_id": f"REQ-{created.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}",
        "title": name,
        "stage": "discovery",
        "created_at": now,
        "updated_at": now,
        "sources": [],
        "requirements": [],
        "metrics": [],
        "acceptance": [],
        "decisions": [],
        "open_questions": [],
        "artifacts": {},
    }
    with record.open("x", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="已安装 PM Forge 的项目目录")
    parser.add_argument("--name", required=True, help="需求名称；同一需求重复调用会返回已有档案")
    args = parser.parse_args()
    try:
        record = initialize(Path(args.project), args.name)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"无法创建需求档案：{error}\n")
    print(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
