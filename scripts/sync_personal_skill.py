#!/usr/bin/env python3
"""Sync the Git-tracked PM workflow skill to the current user's Codex skills."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "edu-pm-workflow"
SOURCE = PROJECT_ROOT / ".agents" / "skills" / SKILL_NAME
DESTINATION = Path.home() / ".codex" / "skills" / SKILL_NAME


def inventory(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.is_dir():
        return result
    for path in root.rglob("*"):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[path.relative_to(root).as_posix()] = digest
    return result


def describe_diff(source: dict[str, str], destination: dict[str, str]) -> list[str]:
    messages = []
    for name in sorted(source.keys() | destination.keys()):
        if name not in destination:
            messages.append(f"个人版缺少：{name}")
        elif name not in source:
            messages.append(f"个人版多出：{name}")
        elif source[name] != destination[name]:
            messages.append(f"内容不同：{name}")
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检查 Git 版本与个人版是否一致（默认）")
    mode.add_argument("--sync", action="store_true", help="把 Git 版本同步到个人 skill 目录")
    parser.add_argument("--yes", action="store_true", help="允许覆盖不同的个人版；仅与 --sync 一起使用")
    args = parser.parse_args()

    if args.yes and not args.sync:
        parser.error("--yes 只能与 --sync 一起使用")
    if not SOURCE.is_dir() or not (SOURCE / "SKILL.md").is_file():
        print(f"找不到 Git 源 skill：{SOURCE}", file=sys.stderr)
        return 1
    if DESTINATION.is_symlink():
        print(f"个人 skill 目录是符号链接，为避免改写其他位置已停止：{DESTINATION}", file=sys.stderr)
        return 1

    source_files = inventory(SOURCE)
    destination_files = inventory(DESTINATION)
    differences = describe_diff(source_files, destination_files)

    if not differences:
        print("个人 skill 与 Git 源版本一致。")
        return 0

    if not args.sync:
        print("个人 skill 与 Git 源版本不一致：")
        for difference in differences:
            print(f"- {difference}")
        print("检查模式未改动文件。需要更新个人版时运行：python3 scripts/sync_personal_skill.py --sync")
        return 1

    if DESTINATION.exists() and not args.yes:
        print("个人版存在差异。同步会用 Git 源版本替换个人副本；确认后运行：")
        print("python3 scripts/sync_personal_skill.py --sync --yes")
        return 2

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    staging = DESTINATION.parent / f".{SKILL_NAME}.sync-staging"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(SOURCE, staging)

    backup = None
    if DESTINATION.exists():
        backup = DESTINATION.parent / f".{SKILL_NAME}.sync-backup"
        if backup.exists():
            shutil.rmtree(backup)
        DESTINATION.rename(backup)
    try:
        staging.rename(DESTINATION)
    except Exception:
        if backup and backup.exists() and not DESTINATION.exists():
            backup.rename(DESTINATION)
        raise
    else:
        if backup and backup.exists():
            shutil.rmtree(backup)

    if inventory(SOURCE) != inventory(DESTINATION):
        print("同步后的内容校验失败。", file=sys.stderr)
        return 1
    print(f"个人 skill 已同步：{DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
