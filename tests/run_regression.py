#!/usr/bin/env python3
"""PM Workflow 回归测试脚本。

用法：
  python3 tests/run_regression.py          # 跑全部 fixtures
  python3 tests/run_regression.py ai-bad   # 只跑单个 fixture

每个 fixture 目录结构：
  tests/fixtures/<name>/
    expectation.json       # 本案例的预期断言（BLOCK数、audit特定错误ID等）
    需求档案.json          # 可选：跑 audit / push_stage 检查
    PRD.html               # 可选：跑 validate_prd 检查

expectation.json 格式（全部字段可选）：
  {
    "validate_prd_fail": bool,
    "validate_prd_contains": ["BLOCK-004", "WARN-005"],
    "audit_contains": ["AIMETRIC-001", "AIETHIC-001", "REF-001"],
    "audit_banned_contains":  ["不允许出现的错误字串"],
    "push_stage": {"from": "defined", "to": "ready", "expected_error_contains": ["BLOCKING"]}
  }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def run_case(fix: Path) -> tuple[bool, list[str]]:
    msgs: list[str] = []
    exp_path = fix / "expectation.json"
    if not exp_path.is_file():
        return True, [f"⏭️  {fix.name}：无 expectation.json，跳过"]
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    ok = True

    rec = fix / "需求档案.json"
    prd = fix / "PRD.html"

    # 1) validate_prd
    if prd.is_file():
        from validate_prd import validate_prd
        try:
            validate_prd(prd.read_text(encoding="utf-8"))
            actual_failed = False
            caught = []
        except ValueError as exc:
            actual_failed = True
            caught = str(exc).splitlines()
        if exp.get("validate_prd_fail") is not None:
            if bool(exp["validate_prd_fail"]) != actual_failed:
                ok = False
                msgs.append(f"❌ {fix.name} validate_prd 预期fail={exp['validate_prd_fail']} 实际fail={actual_failed}")
                for line in caught:
                    msgs.append("   " + line)
        for want in exp.get("validate_prd_contains", []):
            if not any(want in line for line in caught):
                ok = False
                msgs.append(f"❌ {fix.name} validate_prd 输出里没找到：{want}")
                msgs.append(f"   实际输出：{caught[:5]}")

    # 2) audit
    if rec.is_file():
        from pm_requirement import audit
        state = json.loads(rec.read_text(encoding="utf-8"))
        errors = audit(state)
        # codex P2-5：audit_expected_count 精确断言——否则简单案例也会被默认ACC-001等错误蒙混过关
        expected_cnt = exp.get("audit_expected_count")
        if expected_cnt is not None:
            if len(errors) != int(expected_cnt):
                ok = False
                msgs.append(
                    f"❌ {fix.name} audit 错误条数 预期={expected_cnt} 实际={len(errors)}，与预期不符"
                )
                if errors:
                    for e in errors[:12]:
                        msgs.append("   实际: " + e)
        for want in exp.get("audit_contains", []):
            if not any(want in line for line in errors):
                ok = False
                msgs.append(f"❌ {fix.name} audit 应命中 {want}，实际未命中")
                msgs.append(f"   实际 audit {len(errors)} 条：{errors[:10]}")
        for ban in exp.get("audit_banned_contains", []):
            if any(ban in line for line in errors):
                ok = False
                msgs.append(f"❌ {fix.name} audit 不应出现 {ban}，实际命中")
        for want_none in exp.get("audit_contains_none", []):
            if any(want_none in line for line in errors):
                ok = False
                msgs.append(f"❌ {fix.name} audit 禁止包含 {want_none}，实际命中")
        # audit_expected_errors：逐条列出应出现的错误ID，数量也要对
        expected_ids = exp.get("audit_expected_errors", [])
        if expected_ids:
            miss = [eid for eid in expected_ids if not any(eid in line for line in errors)]
            if miss:
                ok = False
                msgs.append(f"❌ {fix.name} audit 预期错误ID没全部命中：缺失 {miss}")
            if len(errors) != len(expected_ids):
                ok = False
                msgs.append(
                    f"❌ {fix.name} audit 错误条数 预期={len(expected_ids)} 实际={len(errors)}，"
                    f"audit_expected_errors 是精确条数断言"
                )

    # 3) push_stage
    ps = exp.get("push_stage")
    if ps and rec.is_file():
        from pm_requirement import _check_stage_push
        state = json.loads(rec.read_text(encoding="utf-8"))
        err = _check_stage_push(ps["from"], ps["to"], state)
        for want in ps.get("expected_error_contains", []):
            if want not in err:
                ok = False
                msgs.append(f"❌ {fix.name} push_stage {ps['from']}→{ps['to']} 应包含「{want}」，实际err={err!r}")
        if ps.get("expected_error_contains") and not err:
            ok = False
            msgs.append(f"❌ {fix.name} push_stage 预期返回错误，实际返回空字符串（通过了，这是错的）")

    if ok:
        msgs.insert(0, f"✅ {fix.name} PASS")
    return ok, msgs


def main(argv):
    cases_root = ROOT / "tests" / "fixtures"
    targets = sorted(p for p in cases_root.iterdir() if p.is_dir())
    if len(argv) > 1:
        targets = [p for p in targets if p.name in argv[1:]]
    if not targets:
        print("没有找到 fixtures 目录")
        return 2
    total, bad = len(targets), 0
    for fix in targets:
        ok, lines = run_case(fix)
        bad += 0 if ok else 1
        for line in lines:
            print(line)
    print(f"\n共 {total} 案例：{total-bad} PASS / {bad} FAIL")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
