#!/usr/bin/env python3
"""把 skill 的资产安装进项目目录——Mac 和 Windows 共用的唯一入口。

三类文件，三种策略：

  RUNTIME  服务运行时代码。**永远覆盖**（带时间戳备份）。
           用户本来就不该手改这些；而「发现本地有改动就保留」恰恰是上一版
           最严重的升级缺陷：旧项目升级时 installed.json 是空的，于是每个
           既有文件都被判为用户定制而保留，服务代码永远停在旧版本，
           表现就是「双击启动脚本没反应 / 导出服务未启动」。

  CUSTOM   用户会主动编辑的（workflow 说明书、PRD 骨架、绘图提示词）。
           内容等于任何一个历史发布版 → 视为没改过，直接升级；
           否则保留用户的文件，新版本写进 .pm-workflow/updates/ 供对照合并。

  ONCE     只在缺失时创建。关键点.md 是项目自己的版本记录，
           .mcp.json.example 是样例，两者都不该被 skill 反复覆盖。

不用 bash：Windows 上没有。所有逻辑都在 Python 里。
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE / "assets/scripts"))
from pm_runtime import VERSION, atomic_write, ensure_config  # noqa: E402

RUNTIME, CUSTOM, ONCE = "runtime", "custom", "once"

# 显式映射，不靠「目录元组 + 特例链」推导。
# 目标路径是被 workflow 文档硬编码引用的（例如 PRD 流程里写死了 scripts/prd-content.html），
# 所以它必须是这里一眼可见、可 grep 的常量，而不是循环里涌现出来的结果。
MAPPING = [
    # ── 服务运行时：缺任何一个，导出/截图就起不来 ──
    ("scripts/pm_runtime.py",              "scripts/pm_runtime.py",              RUNTIME),
    ("scripts/pm_bootstrap.py",            "scripts/pm_bootstrap.py",            RUNTIME),
    ("scripts/start_service.py",           "scripts/start_service.py",           RUNTIME),
    ("scripts/prototype_server.py",        "scripts/prototype_server.py",        RUNTIME),
    ("scripts/prototype_launcher.py",      "scripts/prototype_launcher.py",      RUNTIME),
    ("scripts/pm_launchagent.py",          "scripts/pm_launchagent.py",          RUNTIME),
    ("scripts/prototype-export-client.js", "scripts/prototype-export-client.js", RUNTIME),
    ("scripts/validate_prd.py",            "scripts/validate_prd.py",            RUNTIME),
    ("scripts/pm_requirement.py",           "scripts/pm_requirement.py",           RUNTIME),
    ("scripts/install_launcher.sh",        "scripts/install_launcher.sh",        RUNTIME),
    ("scripts/启动原型导出服务.command",     "启动原型导出服务.command",             RUNTIME),
    ("scripts/启动原型导出服务.bat",         "启动原型导出服务.bat",                 RUNTIME),
    # ── 用户会改的 ──
    ("workflows/edu-pm-prd.md",            ".agents/workflows/edu-pm-prd.md",            CUSTOM),
    ("workflows/edu-pm-demand.md",         ".agents/workflows/edu-pm-demand.md",         CUSTOM),
    ("workflows/edu-pm-acceptance.md",     ".agents/workflows/edu-pm-acceptance.md",     CUSTOM),
    ("workflows/edu-pm-data-analysis.md",  ".agents/workflows/edu-pm-data-analysis.md",  CUSTOM),
    ("workflows/edu-pm-ai-ethics.md",      ".agents/workflows/edu-pm-ai-ethics.md",      CUSTOM),
    ("templates/prd-content.html",         "scripts/prd-content.html",                   CUSTOM),
    ("templates/pencil-draw-prompt.md",    "scripts/pencil-draw-prompt.md",              CUSTOM),
    # ── 只创建一次 ──
    ("templates/关键点.md",                 "关键点.md",                                   ONCE),
    ("config/mcp.json.example",            ".mcp.json.example",                          ONCE),
    ("config/pm-forge.json.example",        "pm-forge.json.example",                      ONCE),
    ("templates/project-constitution.md.example", "PROJECT_CONSTITUTION.md",              ONCE),
    ("templates/.pm-product-context/README.md",      ".pm-product-context/README.md",       ONCE),
    ("templates/.pm-product-context/product.md",     ".pm-product-context/product.md",      ONCE),
    ("templates/.pm-product-context/personas.md",    ".pm-product-context/personas.md",     ONCE),
    ("templates/.pm-product-context/competitors.md", ".pm-product-context/competitors.md",  ONCE),
]

# 参考资料是可选的：老版本仓库里没有 assets/references/，缺了不影响功能。
REFERENCE_DIR = "references"
REFERENCE_TARGET = ".agents/references"

# 需要可执行位。copy2 只保留源文件的模式，而 zip 分发、网盘中转、
# Windows 检出再传回 Mac 都会丢权限位——丢了就是「双击没反应」。
EXECUTABLE = {
    "启动原型导出服务.command",
    "scripts/install_launcher.sh",
    "scripts/start_service.py",
    "scripts/prototype_launcher.py",
}

# 这一项必须排在 MAPPING 的运行时段里，但单独列出来做个说明：
# 注册 LaunchAgent 时 plist 指向的是项目里的 prototype_launcher.py，
# 所以文件必须先落地、再注册，顺序不能颠倒。
LAUNCHER_SCRIPT = "scripts/prototype_launcher.py"

# 上一代留下的文件：留着会误导用户去跑一个装「全局唯一 label」LaunchAgent 的旧脚本
# （那会让一台机器只能服务一个项目）。移走而不是直接删，放进备份目录。
STALE = ["scripts/setup_prototype_export_watcher.sh"]

GITIGNORE = ["/.pm-workflow/", "/scripts/pm-runtime-config.js", "/scripts/.venv/", "/.handoff/"]

# Windows 的 core.autocrlf=true 检出后再传回 Mac，.command 会带上 CRLF，
# bash 报 `$'\r': command not found`；.bat 反过来需要 CRLF 才可靠。
GITATTRIBUTES = [
    "* text=auto",
    "*.command text eol=lf",
    "*.sh text eol=lf",
    "*.bat text eol=crlf",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def load_known_hashes():
    """历代已发布版本的内容 hash：让「文件等于某个旧版本」被认成没改过而直接升级，
    而不是误判成用户定制。缺这个文件不致命，只是升级时更容易报冲突。"""
    path = Path(__file__).resolve().parent / "known_hashes.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def make_executable(path):
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass  # Windows 上没有可执行位，失败不算问题


def setup_launcher(root, config, say):
    """在 macOS 上注册按需启动器，让点导出能自动起服务。

    默认就做，因为它不是常驻进程：端口归 launchd 持有，空闲时项目里没有任何
    进程在跑（详见 pm_launchagent.py 顶部说明）。

    **任何失败都只警告、不阻断安装。** 装 skill 的人可能没权限写
    ~/Library/LaunchAgents、可能在没有 launchctl 的沙箱里、可能根本不是 macOS——
    这些都不该让「文件装好了」这件事失败。丢了它只是回退到手动双击启动。
    """
    if not sys.platform == "darwin":
        return
    try:
        sys.path.insert(0, str(root / "scripts"))
        import pm_launchagent
        ok, detail = pm_launchagent.install(root, config)
    except Exception as error:  # noqa: BLE001 — 见上：绝不阻断安装
        say(f"   ⚠️  按需启动器注册失败（{error}）")
        say("      不影响导出：双击「启动原型导出服务.command」照常可用。")
        return
    if ok:
        say(f"   ✅ 按需启动器已注册：点导出/一键复制全文会自动起服务，无需先双击")
        say(f"      空闲时不占进程；不想要就跑 bash scripts/install_launcher.sh --uninstall")
    else:
        say(f"   ⚠️  按需启动器注册失败（{detail}）")
        say("      不影响导出：双击「启动原型导出服务.command」照常可用。")


def install(root, quiet=False, with_launcher=True):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    say = (lambda *a: None) if quiet else print

    manifest_path = root / ".pm-workflow/installed.json"
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    tracked = previous.get("files", {}) if isinstance(previous, dict) else {}
    known = load_known_hashes()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = root / ".handoff/skill-backups" / f"init-{stamp}"

    entries = list(MAPPING)
    # Path.glob 对不存在的目录返回空列表，所以这里不需要额外的存在性判断。
    for path in sorted((SOURCE / "assets" / REFERENCE_DIR).glob("*")):
        if path.is_file():
            entries.append((f"{REFERENCE_DIR}/{path.name}",
                            f"{REFERENCE_TARGET}/{path.name}", CUSTOM))

    for name in ("scripts", ".handoff"):
        (root / name).mkdir(parents=True, exist_ok=True)

    created, updated, current, skipped, conflicts, missing = [], [], [], [], [], []

    for source_rel, dest_rel, kind in entries:
        source = SOURCE / "assets" / source_rel
        if not source.is_file():
            missing.append(source_rel)
            continue
        dest = root / dest_rel
        incoming, existing = digest(source), digest(dest)

        if existing == incoming:
            tracked[dest_rel] = incoming
            current.append(dest_rel)
            if dest_rel in EXECUTABLE:
                make_executable(dest)
            continue

        if existing is not None:
            if kind == ONCE:
                skipped.append(dest_rel)
                continue
            if kind == CUSTOM:
                # 认得出是某个历史发布版 → 用户没改过 → 照常升级
                unchanged = existing == tracked.get(dest_rel) or existing in known.get(source_rel, [])
                if not unchanged:
                    proposal = root / ".pm-workflow/updates" / dest_rel
                    proposal.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, proposal)
                    conflicts.append(dest_rel)
                    continue
            backup = backup_root / dest_rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        if dest_rel in EXECUTABLE:
            make_executable(dest)
        (updated if existing is not None else created).append(dest_rel)
        tracked[dest_rel] = incoming

    retired = []
    for rel in STALE:
        path = root / rel
        if path.is_file():
            target = backup_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            tracked.pop(rel, None)
            retired.append(rel)

    atomic_write(manifest_path, json.dumps(
        {"version": VERSION, "files": tracked, "pending_updates": conflicts},
        ensure_ascii=False, indent=2))

    _write_lines(root / ".gitignore", GITIGNORE)
    _write_lines(root / ".gitattributes", GITATTRIBUTES)
    keep = root / ".handoff/.gitkeep"
    if not any(root.joinpath(".handoff").iterdir()):
        keep.touch()

    config = ensure_config(root)

    say(f"✅ PM Workflow {VERSION} 已安装到 {root}")
    say(f"   项目标识 {config['project_id']}，服务端口 {config['port']}")
    for label, items in (("新增", created), ("更新", updated), ("已是最新", current),
                         ("已存在未覆盖", skipped), ("移入备份", retired)):
        if items:
            say(f"   {label} {len(items)} 项" + ("：" + "、".join(items) if len(items) <= 4 else ""))
    if missing:
        say(f"   ⚠️  skill 里缺少 {len(missing)} 个资产文件：{'、'.join(missing)}")
    if conflicts:
        say("   ⚠️  以下文件你改过，已保留你的版本；新版放在 .pm-workflow/updates/ 供对照：")
        for item in conflicts:
            say("        " + item)
    if (root / "scripts/.venv").is_dir():
        say("   💡 scripts/.venv 是旧版留下的（约 150MB），现在运行环境放在用户目录共享，可以删掉")

    launcher_ready = False
    if with_launcher:
        setup_launcher(root, config, say)
        launcher_ready = _launcher_ready(root, config)

    say("")
    if os.name == "nt":
        say("下一步：双击项目根目录的「启动原型导出服务.bat」，保持窗口开着")
        say("排查问题：py -3 scripts\\start_service.py --doctor")
    elif launcher_ready:
        say("下一步：直接打开原型或 PRD 点导出即可——服务会自动启动。")
        say("        （也可以双击「启动原型导出服务.command」手动起，效果一样）")
        say("排查问题：python3 scripts/start_service.py --doctor")
    else:
        say("下一步：双击项目根目录的「启动原型导出服务.command」，保持窗口开着")
        say("排查问题：python3 scripts/start_service.py --doctor")
    return 0


def _launcher_ready(root, config):
    try:
        sys.path.insert(0, str(root / "scripts"))
        import pm_launchagent
        registered, _port, matched, _pid = pm_launchagent.status(config)
        return registered and matched
    except Exception:  # noqa: BLE001
        return False


def _write_lines(path, entries):
    """逐行补齐，不覆盖用户已有内容。"""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = text.splitlines()
    added = [entry for entry in entries if entry not in lines]
    if not added:
        return
    body = text.rstrip("\n")
    atomic_write(path, (body + "\n" if body else "") + "\n".join(added) + "\n")


def release(args):
    """发布模式：bump VERSION + 刷新 known_hashes + 源vs安装版一致性检查。

    codex P1-3：任何写入前必须先跑致命检查（缺源文件 / 源≠安装版漂移），
    任何一项失败 sys.exit(1)，**严禁** 改 VERSION / known_hashes。
    """
    skill_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(skill_root / "assets" / "scripts"))
    import pm_runtime  # noqa: E402

    project = Path(args.project).resolve() if args.project else None
    installed_root = project if project and (project / "scripts" / "pm_requirement.py").is_file() else None

    entries = list(MAPPING)
    for path in sorted((skill_root / "assets" / REFERENCE_DIR).glob("*")):
        if path.is_file():
            entries.append((f"{REFERENCE_DIR}/{path.name}", f"{REFERENCE_TARGET}/{path.name}", CUSTOM))
    source_hashes: dict[str, str] = {}
    missing_sources = []
    for src_rel, _dst, _k in entries:
        p = skill_root / "assets" / src_rel
        if not p.is_file():
            missing_sources.append(src_rel)
            continue
        source_hashes[src_rel] = digest(p)
    known_path = Path(__file__).resolve().parent / "known_hashes.json"
    known_old = load_known_hashes()

    ver_path = skill_root / "assets" / "scripts" / "pm_runtime.py"
    ver_old = pm_runtime.VERSION
    parts = ver_old.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        print(f"❌ VERSION 格式异常：{ver_old}，需要 X.Y.Z")
        return 2
    ver_new = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"

    drift = []
    if installed_root:
        for src_rel, dst, _k in entries:
            src_p = skill_root / "assets" / src_rel
            inst_p = installed_root / dst
            if not inst_p.is_file() or not src_p.is_file():
                continue
            if digest(inst_p) != digest(src_p):
                drift.append((dst, "≠", src_rel))
    skipped_install_check = not installed_root

    header = f"== PM Workflow Release {'[DRY-RUN]' if args.dry_run else ''} =="
    print(header)
    print(f"  当前版本：{ver_old} → {ver_new}")
    print(f"  源文件数量：{len(source_hashes)}，缺源文件：{len(missing_sources)}")
    if missing_sources:
        for m in missing_sources:
            print("     缺源：", m)

    fatal = False
    if missing_sources:
        fatal = True
        print(f"  ❌ 发现 {len(missing_sources)} 个缺源文件，必须先补源再发布")
    if skipped_install_check:
        print(f"  ⚠️  未提供 --project 或该目录未安装，跳过源/安装一致性检查")
    elif drift:
        fatal = True
        print(f"  ❌ 检测到 {len(drift)} 个文件「安装版 ≠ 源版」，先反向同步再发布：")
        for dst, _, src in drift:
            print(f"      - {dst}  ↔  {src}")
    else:
        print("  ✅ 源/安装一致性检查通过")

    # codex P1-3：dry-run和真发布共用同一个致命检查
    if fatal:
        if args.dry_run:
            print("\n  [DRY-RUN] 检查未通过，未写入")
        else:
            print("\n  ❌ 检查未通过，任何文件未修改；先修问题再 release")
        return 1

    if args.dry_run:
        print("\n  [DRY-RUN] 检查全部通过；去掉 --dry-run 再真发布")
        return 0

    text = ver_path.read_text(encoding="utf-8")
    if f'VERSION = "{ver_old}"' not in text:
        print("❌ pm_runtime.py 中找不到 VERSION 行，拒绝写入")
        return 3
    text = text.replace(f'VERSION = "{ver_old}"', f'VERSION = "{ver_new}"', 1)
    ver_path.write_text(text, encoding="utf-8")
    print(f"  ✅ VERSION bumped: {ver_old} → {ver_new}")

    merged = dict(known_old)
    for rel, h in source_hashes.items():
        arr = list(merged.get(rel, []))
        if h not in arr:
            arr.append(h)
        merged[rel] = arr
    with known_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"  ✅ known_hashes.json 已刷新（共 {len(merged)} 个源文件）")

    print(f"\n发布完成：PM Workflow {ver_new}。下一步：git commit + tag v{ver_new}")
    return 0


if __name__ == "__main__":
    # codex P1-2：兼容旧入口调用方式——
    #   旧格式：initialize.py --project <dir> [--quiet] [--no-launcher]  (不带 install 子命令)
    #   新格式：initialize.py install --project <dir> ...
    #   无参数：默认 install 当前目录
    #
    # 处理策略：如果第一个位置参数不是子命令名（install/release/-h/--help），
    # 就把整个argv前插入"install"，当作install模式跑，保证老脚本/老README不炸
    argv = sys.argv[1:]
    if len(argv) == 0:
        argv = ["install"]
    else:
        first = argv[0]
        if first not in ("install", "release", "-h", "--help") and first.startswith("-") or \
           first not in ("install", "release", "-h", "--help") and not first.startswith("-"):
            if not any(a in ("install", "release") for a in argv):
                argv = ["install"] + argv

    parser = argparse.ArgumentParser(description="把 PM Workflow 安装进项目目录")
    # 顶层也暴露 install 的常用参数，便于旧命令 initialize.py --project . 也能正常解析
    parser.add_argument("--project", default=".", help="项目目录，默认当前目录（install 模式生效）")
    parser.add_argument("--quiet", action="store_true", help="安静模式（install 模式生效）")
    parser.add_argument("--no-launcher", action="store_true",
                        help="install 模式：不注册 macOS 按需启动器（点导出前需手动双击启动入口）")
    sub = parser.add_subparsers(dest="mode", help="运行模式：install（默认）/ release（发布新版本）")
    install_p = sub.add_parser("install", help="默认模式：安装到项目")
    install_p.add_argument("--project", default=".", help="项目目录，默认当前目录")
    install_p.add_argument("--quiet", action="store_true")
    install_p.add_argument("--no-launcher", action="store_true",
                           help="不注册 macOS 按需启动器（点导出前需手动双击启动入口）")
    release_p = sub.add_parser("release", help="发布模式：bump 版本号 + 刷新 known_hashes + 检查源/安装版一致性")
    release_p.add_argument("--dry-run", action="store_true", help="只检查不写版本号和 known_hashes")
    release_p.add_argument("--project", default=".", help="可选：提供已安装项目路径，用于和最新源做diff比对")
    args = parser.parse_args(argv)

    if args.mode in (None, "install"):
        # 顶层参数 vs install子parser参数：以子parser写的优先，没写才用顶层
        project = getattr(args, "project", ".") or "."
        quiet = bool(getattr(args, "quiet", False))
        with_launcher = not bool(getattr(args, "no_launcher", False))
        sys.exit(install(project, quiet=quiet, with_launcher=with_launcher))
    sys.exit(release(args))
