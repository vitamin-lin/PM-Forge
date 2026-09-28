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
import copy
import subprocess
import sys
import tempfile
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

    # 4) sync_acceptance_from_prd（codex P1-1/P1-2新增）
    sync_cfg = exp.get("sync_acceptance_from_prd")
    if sync_cfg and rec.is_file():
        prd_file = fix / sync_cfg.get("prd_file", "PRD.html")
        if prd_file.is_file():
            from pm_requirement import _sync_acceptance_from_prd
            state = json.loads(rec.read_text(encoding="utf-8"))
            # 备份acceptance以便检查是否污染
            acc_before = json.loads(json.dumps(state.get("acceptance", [])))
            want_fail = sync_cfg.get("expected_error_contains")
            try:
                n = _sync_acceptance_from_prd(state, prd_file)
                err = ""
                updated = n
            except ValueError as exc:
                err = str(exc)
                updated = -1
            for want in want_fail or []:
                if want not in err:
                    ok = False
                    msgs.append(f"❌ {fix.name} sync_acceptance 错误信息应包含「{want}」，实际err={err[:90]!r}…")
            if sync_cfg.get("expect_error") and not err:
                ok = False
                msgs.append(f"❌ {fix.name} sync_acceptance 预期抛错，实际成功 updated={updated}")
            if sync_cfg.get("expect_no_touch"):
                acc_after = state.get("acceptance", [])
                if json.dumps(acc_before, sort_keys=True) != json.dumps(acc_after, sort_keys=True):
                    ok = False
                    msgs.append(f"❌ {fix.name} sync_acceptance 预期不碰 acceptance，但实际修改了内容")

    # 5) parse_acceptance_count（codex P1-1新增）
    parse_cfg = exp.get("parse_acceptance")
    if parse_cfg:
        prd_file = fix / parse_cfg.get("prd_file", "PRD.html")
        if prd_file.is_file():
            from pm_requirement import _parse_prd_html_acceptance
            rows = _parse_prd_html_acceptance(prd_file)
            expected_n = parse_cfg.get("expected_count")
            if expected_n is not None and len(rows) != int(expected_n):
                ok = False
                msgs.append(f"❌ {fix.name} 验收解析预期 {expected_n} 条，实际 {len(rows)} 条（overview等普通行是否污染？）")
            only_aids = parse_cfg.get("only_aids")
            if only_aids:
                aids_parsed = sorted(a for a, _r, _s, _e in rows if a)
                if aids_parsed != sorted(only_aids):
                    ok = False
                    msgs.append(f"❌ {fix.name} 验收解析A-IDs 预期 {sorted(only_aids)} 实际 {aids_parsed}")
            if parse_cfg.get("validate_table_contract"):
                from validate_prd import validate_prd

                def acceptance_errors(content):
                    try:
                        validate_prd(content)
                    except ValueError as exc:
                        return [line for line in str(exc).splitlines() if "验收条件表" in line]
                    return []

                content = prd_file.read_text(encoding="utf-8")
                contract_errors = acceptance_errors(content)
                if contract_errors:
                    ok = False
                    msgs.append(f"❌ {fix.name} 合法 acceptance-table 不应产生验收表错误：{contract_errors}")
                invalid_content = content.replace(
                    'class="acceptance-table"', 'class="rule-table"', 1
                )
                invalid_errors = acceptance_errors(invalid_content)
                if not any("缺少验收条件表" in line for line in invalid_errors):
                    ok = False
                    msgs.append(f"❌ {fix.name} 缺少 acceptance-table class 时校验器应阻塞：{invalid_errors}")

    # 6) 组合 CLI 更新：校验最终候选状态，失败不落盘
    cli_cfg = exp.get("cli_stage_updates")
    if cli_cfg and rec.is_file():
        base_state = json.loads(rec.read_text(encoding="utf-8"))
        for case in cli_cfg.get("cases", []):
            with tempfile.TemporaryDirectory(prefix="pm-forge-cli-") as temp_dir:
                project = Path(temp_dir)
                candidate = copy.deepcopy(base_state)
                candidate.update(case.get("record_overrides", {}))
                record_path = project / "需求档案.json"
                original = json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
                record_path.write_text(original, encoding="utf-8")
                command = [
                    sys.executable, str(ROOT / "scripts" / "pm_requirement.py"),
                    "--project", str(project), "--name", "CLI 回归", "--requirement-dir", ".", "--update",
                    *case.get("args", []),
                ]
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                output = result.stdout + result.stderr
                expected_exit = int(case.get("expected_exit", 0))
                if result.returncode != expected_exit:
                    ok = False
                    msgs.append(
                        f"❌ {fix.name} CLI {case['name']} 预期退出码 {expected_exit}，"
                        f"实际 {result.returncode}：{output[-500:]}"
                    )
                for want in case.get("output_contains", []):
                    if want not in output:
                        ok = False
                        msgs.append(f"❌ {fix.name} CLI {case['name']} 输出缺少「{want}」：{output[-500:]}")
                saved = json.loads(record_path.read_text(encoding="utf-8"))
                if case.get("expect_unchanged") and record_path.read_text(encoding="utf-8") != original:
                    ok = False
                    msgs.append(f"❌ {fix.name} CLI {case['name']} 失败后需求档案被改写")
                if "expected_stage" in case and saved.get("stage") != case["expected_stage"]:
                    ok = False
                    msgs.append(
                        f"❌ {fix.name} CLI {case['name']} stage 预期 {case['expected_stage']}，实际 {saved.get('stage')}"
                    )
                if "expected_latest_basis" in case:
                    decisions = saved.get("decisions", [])
                    actual_basis = decisions[-1].get("basis_ids") if decisions else None
                    if actual_basis != case["expected_latest_basis"]:
                        ok = False
                        msgs.append(
                            f"❌ {fix.name} CLI {case['name']} 最后决策依据预期 {case['expected_latest_basis']}，实际 {actual_basis}"
                        )

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
