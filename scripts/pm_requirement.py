#!/usr/bin/env python3
"""创建 / 更新 / 审计 PM Forge 需求档案。

用法：
    # 新建或复用需求档案（原行为，未破坏兼容性）
    python3 pm_requirement.py --project <产品项目根> --name <需求名> \
        [--requirement-dir <相对路径> | --requirement-dir .]

    # 【新增】更新需求档案（阻塞性写入，失败就报错不写）
    python3 pm_requirement.py --project . --name "<需求名>" --update \
        [--push-stage defined|ready|shipped|measured|closed] \
        [--add-decision "<决策摘要>" [--basis-ids SRC-001,R-003] \
                                [--choice continue|iterate|stop|scope_changed|boundary_confirmed] \
                                [--next-action "<后续动作>"] \
                                [--decided-by "产品团队"]] \
        [--sync-acceptance-from-prd "<REQ_DIR相对/需求文档/xxx-PRD.html>"]

    # 【新增】审计需求档案（只读，校验跨字段一致性 + 规范合规）
    python3 pm_requirement.py --project . --name "<需求名>" --audit

退出码：0 = 通过；1 = 阻塞性错误（stage 跳级、A-xxx 不匹配等）。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


CONFIG_NAME = "pm-forge.json"
RECORD_NAME = "需求档案.json"
STAGE_ORDER = ["discovery", "defined", "ready", "shipped", "measured", "closed"]
VALID_CHOICES = {"continue", "iterate", "stop", "scope_changed", "boundary_confirmed"}
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


def _load_record(record_path: Path) -> dict:
    existing = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(existing, dict) or not existing.get("requirement_id"):
        raise ValueError(f"已有需求档案缺少 requirement_id：{record_path}")
    return existing


def _save_record(record_path: Path, state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = record_path.with_suffix(record_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(record_path)


def _ensure_product_context(project: Path) -> None:
    """项目根第一次创建需求时：从SKILL模板复制 product/personas/competitors + constitution + README。
    若项目根已有 `.pm-product-context/product.md`（用户自己建过），什么都不做（绝不覆盖）。
    """
    ctx = project / ".pm-product-context"
    if (ctx / "product.md").is_file():
        return  # 用户有内容，不覆盖

    # 模板搜索顺序：本脚本旁边（用户直接用scripts/下版本）→ skill assets/templates/.pm-product-context/
    # → 全局安装的 skill 目录 → 都找不到就用内置 fallback 字符串写，保证功能可用。
    template_candidates = [
        Path(__file__).resolve().parent.parent
        / ".agents/skills/edu-pm-workflow/assets/templates/.pm-product-context",
        Path(__file__).resolve().parent  # 没找到就算了，下面会走 fallback
        / ".pm-product-context-templates",
    ]
    template_dir = next((p for p in template_candidates if p.is_dir()), None)

    ctx.mkdir(parents=True, exist_ok=True)

    def _write_if_missing(filename: str, fallback: str) -> None:
        target = ctx / filename
        if target.is_file():
            return
        src = template_dir / filename if template_dir else None
        if src and src.is_file():
            target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            target.write_text(fallback, encoding="utf-8")

    # README 说明
    _write_if_missing("README.md", PRODUCT_CTX_README_FALLBACK)
    # product.md（宪法级事实）
    _write_if_missing("product.md", PRODUCT_CTX_PRODUCT_FALLBACK)
    # personas.md（可选详情）
    _write_if_missing("personas.md", PRODUCT_CTX_PERSONAS_FALLBACK)
    # competitors.md（可选详情）
    _write_if_missing("competitors.md", PRODUCT_CTX_COMPETITORS_FALLBACK)

    # 同目录还放一份 Project Constitution 示例（spec-kit 灵感），供大型项目单独引用
    constitution_src = None
    if template_dir and template_dir.parent.is_dir():
        c = template_dir.parent / "project-constitution.md.example"
        if c.is_file():
            constitution_src = c
    const_target = project / "PROJECT_CONSTITUTION.md"
    if not const_target.is_file():
        if constitution_src:
            const_target.write_text(constitution_src.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            const_target.write_text(PROJECT_CONSTITUTION_FALLBACK, encoding="utf-8")


PRODUCT_CTX_README_FALLBACK = """# 产品上下文自动读取（mySecond.ai 同款设计）
本目录存放「跨需求不变」的产品级事实。所有PM-Forge工作流启动前会先尝试读下面3份文件，读到就自动注入上下文，读不到不报错。

## 文件清单（全部可选，空文件会被忽略）
- `product.md`       产品宪法：一句话定位/画像/技术栈/合规红线/已拍板决策/术语表/竞品锚点
- `personas.md`      主/次用户画像详情版（如果宪法里的Persona-A需要扩展）
- `competitors.md`   完整竞品分析（如果宪法里的5家表格不够用）

## 更新原则
1. 只改「跨需求不变」的东西：单个需求专属背景放那个需求的沟通记录/PRD，别放这里。
2. 术语改了就全局同步：Glossary里加了新同义词，立刻改，否则下次AI又会混用。
3. 已拍板决策要附依据：DC-001这样的决策不能只写结论，要写「当时为什么拍的」，下次要不要重开才有判断依据。
"""

PRODUCT_CTX_PRODUCT_FALLBACK = """# 产品宪法 · （替换为真实项目名）

> 📋 自动读取：PM-Forge 工作流启动时，会先把本文件内容注入上下文，作为本项目「跨需求不变」的共享事实。
> 若有冲突，以本文件为准（而不是每个需求重讲一遍背景）。

## 一、一句话定位
> 例：给连锁教育机构的前台老师，通过自动填报销/开课单据，把每天30分钟行政记账压缩到5分钟。
- （待填）

## 二、主/次用户画像
> Primary = 核心用户（功能优先满足他）；Secondary = 次要用户（体验要照顾但不阻塞主线）

### Primary Persona-A
- Who（真实人群+岗位）：（待填）
- Problem（最痛的1-3件事）：（待填）
- Goal（用了你产品想达成什么）：（待填）
- Current（现在怎么解决）：（待填）

### Secondary Persona-B
- Who：（待填）
- 为什么是次要：（待填）
- 我们关心他的哪部分：（待填）

## 三、技术栈 & 合规红线（不可妥协项）
### 3.1 技术栈硬约束
- 前端：（例：Taro 跨端小程序 / React 18 + Vite…）
- 后端：（例：Nest.js / Supabase / 纯前端离线…）
- 数据存储：（例：Postgres 16 + Prisma / localStorage…）
- 绝对不允许引入：（例：jQuery / 未审计的闭源三方SDK…）

### 3.2 AI合规红线（AI类项目必填；否则 AIETHIC-001 审计阻塞）
- PII 范围（哪些算可识别用户信息）：手机号 / 身份证 / 姓名 / 组织 / 交易记录…（待填）
- 模型白名单（非白名单一律不允许调用）：（例：仅境内通过等保2.0的模型服务…）
- EU AI Act 风险等级：Unacceptable / High / General / Minimal（待填）
- 可追溯要求（每次模型调用是否强制留痕）：（待填，是/否 + request_id 字段名）

### 3.3 已拍板不做的共享决策（避免每个需求重谈一遍）
| Decision ID | 结论 | 当时依据 | 触发重谈的条件 |
|---|---|---|---|
| DC-001（示例） | 一期不做多角色权限 | 当前客户都是3人以下小团队 | 有付费客户明确要求≥5角色权限 |

## 四、术语表（全项目同名同物；不一致就以这里为准）
| 中文术语 | 精确定义 | 英文/缩写 | 禁止混用的写法 |
|---|---|---|---|
| （示例）单据 | 任一用户提交的结构化表单记录 | Doc / Document | 表单、票、条目、流水 |

## 五、竞品锚点（≤5家；重点写「明确不跟抄的点」）
| 竞品 | 一句话定位 | 我们和他的核心差异 | 明确不跟抄的功能 |
|---|---|---|---|
| （示例）钉钉OA | 通用大中台组织管理工具 | 我们只做培训学校前台场景 | 审批流、通讯录、打卡 |
"""

PRODUCT_CTX_PERSONAS_FALLBACK = """# 主/次用户画像（详情版，可选填写）
> 如果 product.md 的 Persona-A / Persona-B 四行讲不清，就填这个文件；否则可以删掉。

---

## Persona-A · 核心用户（必填姓名+背景）
- 姓名：
- 年龄/从业年限：
- 日常工作场景：
- 一天中最痛的 3 个时刻：
  1.
  2.
  3.
- 他会在什么情况下放弃我们产品？
- 他愿意为哪件事真金白银付费？

---

## Persona-B · 次要用户
- 姓名/角色：
- 为什么不直接服务他？
- 哪 1-2 个交互点我们必须照顾他体验？
"""

PRODUCT_CTX_COMPETITORS_FALLBACK = """# 竞品分析（详情版，可选填写）
> 如果 product.md 的 5 家竞品表格不够，就填这个文件；否则可以删掉。

---

## 竞品 1 · （名称）
- 官网/下载：
- 一句话定位：
- 月活 / 客单价（能查到的话）：
- **做得最好的 3 件事（我们可以学习）**：
  1.
  2.
  3.
- **明确不跟抄的 2 件事（为什么）**：
  1.
  2.
- 它没做、但客户反复提的 1 件事（我们的机会）：

---

（重复竞品 1 的结构继续添加，≤5 家为宜）
"""

PROJECT_CONSTITUTION_FALLBACK = """<!-- 项目产品宪法（Project Constitution，灵感自 github/spec-kit SDD 方法论）
    作用：本项目所有共享规则只改这一份文件，开每个需求前自动读，避免每次重复讲背景。
    原则：这里只写 **跨需求不变** 的事实；单个需求专属内容（背景、方案、验收）放需求自己的 PRD。
-->
# 产品宪法 · <PROJECT_NAME_PLACEHOLDER>

## 一、产品一句话定位（一句话，给AI/人都能看懂）
> 请在此填写：一句话说清本产品「给谁，解决什么问题，怎么带来价值」
>
> 示例：「给连锁教育机构的前台老师，通过自动填报销/开课单据，把每天30分钟行政记账压缩到5分钟。」

## 二、主/次用户画像（Context Ark PRD Template 推荐的 Primary/Secondary 结构）
> 每条画像 = Who（真实人群+职位名）+ Problem（他最痛的那件事）+ Goal（用了你产品想达到什么）+ Current（现在怎么解决）

### Primary（核心用户，功能优先满足他）
| ID | Who | 核心问题 Problem | 用后目标 Goal | 当前替代 Current |
|---|---|---|---|---|
| Persona-A |  |  |  |  |

### Secondary（次要用户，不阻塞主线但体验要照顾）
| ID | Who | 为什么是次要 | 我们关心他的哪部分 |
|---|---|---|---|
| Persona-B |  |  |  |

## 三、非妥协的技术栈与合规红线（spec-kit Constitution 对应项）
> 只写「无论什么需求都不能破」的硬规则；可商量的写在后面。

### 3.1 技术栈硬约束
- 前端框架：（例：React 18 / Taro 跨端小程序 / Vue3 + Vite…）
- 后端服务：（例：Nest.js / Go gin / 无服务端纯浏览器…）
- 数据层：（例：Postgres 16 + Prisma / Supabase / localStorage…）
- **绝对不能引入的依赖**：（例：jQuery / 闭源三方闭源SDK 无审计…）

### 3.2 合规红线（AI产品必须填写，否则 AIETHIC-001 审计失败）
- PII 范围：哪些字段算用户可识别信息？（手机号/身份证/姓名/组织/交易记录…）
- 数据出境：是否允许走境外模型？境内模型白名单有哪些？
- EU AI Act 等级：本产品属于哪个等级（Unacceptable / High / General / Minimal）？
- 审计可追溯：是否要求每次模型调用留痕 request_id × user_id？

### 3.3 已拍板不做的共享决策（避免每个需求都讨论一遍）
| Decision ID | 结论 | 当时依据 | 什么时候才重开讨论 |
|---|---|---|---|
| DC-001（例） | 不在一期做多角色权限 | 客户都是3人以下小团队，不需要 | 有客户要求5+角色权限时 |

## 四、术语表（Glossary，全项目同名同物，避免A说"计划"B说"方案"）
| 术语（中文） | 定义 | 英文/缩写 | 禁止混用的写法 |
|---|---|---|---|
| （例）单据 | 任一用户提交的结构化表单记录 | Doc / Document | 不许叫：表单/票/条目 等 |

## 五、竞品锚点（competitors.md 摘要，自动读入上下文）
> 写5家以内即可；重点：**我们明确不跟谁比**（避免每次需求都有人提"你看XX都做了"）。

| 竞品 | 一句话定位 | 我们和他哪不一样 | 明确不跟抄的点 |
|---|---|---|---|
| （例）钉钉OA | 通用大中台组织管理工具 | 我们只做培训学校前台场景 | 绝不做：审批流、通讯录、打卡 |
"""

def initialize(project: Path, name: str, requirement_dir: Optional[str] = None,
               init_product_context: bool = True) -> Path:
    """创建空需求档案或返回已有档案路径（保留 100% 向后兼容）。

    init_product_context=True（默认）时：如果是**第一次在该项目创建需求档案**（即项目根
    `.pm-product-context/` 目录还不存在），就把 SKILL 里的 3 份模板（product/personas/competitors）
    + README 说明 + Project Constitution 复制到项目根，后续每次工作流启动前自动读入。
    老项目已经有 `.pm-product-context/product.md` 时，什么都不做（绝不覆盖用户写过的内容）。
    """
    project = project.resolve()
    if not project.is_dir():
        raise ValueError(f"项目目录不存在：{project}")
    name = requirement_name(name)
    if init_product_context:
        try:
            _ensure_product_context(project)
        except OSError:
            pass  # 模板复制失败不阻塞核心的需求档案创建（最差用户下回手动填）
    if requirement_dir is None:
        root = artifact_root(project)
        target = (root / name).resolve()
        if not target.is_relative_to(root):
            raise ValueError("需求目录超出产物目录")
    else:
        relative = Path(requirement_dir)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("requirement-dir 必须是项目内已有目录的相对路径")
        target = (project / relative).resolve()
        if not target.is_relative_to(project) or not target.is_dir():
            raise ValueError("requirement-dir 必须指向项目内已有的需求目录")
    record = target / RECORD_NAME
    if record.is_file():
        _load_record(record)
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


# =========================================================
# -- 更新命令实现（阻塞性写入）
# =========================================================

def _check_stage_push(current: str, target: str, state: dict) -> str:
    if current == target:
        return ""
    if STAGE_ORDER.index(target) < STAGE_ORDER.index(current):
        return f"stage 不可回退：{current} → {target}"
    if STAGE_ORDER.index(target) - STAGE_ORDER.index(current) > 1:
        nxt = STAGE_ORDER[STAGE_ORDER.index(current) + 1]
        return f"stage 不得跳级：{current} → {target}（先到 {nxt}）"
    if current == "discovery" and target == "defined":
        art = state.get("artifacts", {})
        has_proto = any(k.startswith("prototype") and bool(v) for k, v in art.items())
        if not (art.get("prd") and has_proto):
            return "artifacts 缺 PRD/原型路径，推到 defined 前必须至少有 PRD + 原型两件产物登记"
    if current == "defined" and target == "ready":
        oq = state.get("open_questions", [])
        blocking_oq = [q for q in oq if str(q.get("labels", []) + [q.get("priority", "")]).find("BLOCKING") >= 0
                       or q.get("priority") == "BLOCKING" or "BLOCKING" in [t.upper() for t in q.get("tags", [])]]
        blocking_open = [q for q in blocking_oq if q.get("status") != "closed"]
        if blocking_open:
            ids = ", ".join(q["id"] for q in blocking_open if q.get("id"))
            return f"BLOCKING 待确认问题未全部关闭（剩 {len(blocking_open)} 条 {ids}），" \
                   "阻塞问题不清零不能进入 ready"
        r_evidence = False
        rid_to_src = {r["id"]: set(r.get("source_ids", [])) for r in state.get("requirements", [])}
        for s in state.get("sources", []):
            if s.get("classification") == "evidence":
                if any(s["id"] in src_set for src_set in rid_to_src.values()):
                    r_evidence = True
                    break
        if not r_evidence:
            return "requirements 中没有任何一条挂了 evidence 级 sources，至少 1 条需求要有真实证据支撑才能进 ready"
        for m in state.get("metrics", []):
            if not m.get("baseline_plan"):
                return (f"metric {m.get('id')} 缺 baseline_plan（谁/怎么/何时拿到基线），"
                        "ready 前每个指标都要有获取路径")
    if current == "ready" and target == "shipped":
        acc = state.get("acceptance", [])
        if not acc:
            return "acceptance 为空，必须先登记验收项再推 shipped"
        p0_total = sum(1 for a in acc if a.get("priority") == "P0")
        p0_passed = sum(1 for a in acc if a.get("priority") == "P0" and a.get("status") == "passed")
        if p0_total > 0 and p0_passed < p0_total:
            return f"P0 验收通过 {p0_passed}/{p0_total}，全部 P0 必须通过才能进入 shipped"
        # codex P2-4：P0/P1 级任何失败都不允许进 shipped（只允许 P2/P3 可有遗留）；比例≥80%去掉<3下限——即使1条也100%
        p1_failed = sum(1 for a in acc if a.get("priority") in ("P0", "P1") and a.get("status") != "passed")
        if p1_failed > 0:
            failed_ids = ", ".join(a.get("id", "?") for a in acc if a.get("priority") in ("P0", "P1") and a.get("status") != "passed")
            return f"P0/P1 验收有 {p1_failed} 条未通过（{failed_ids}），P0/P1 未通过时不得进入 shipped；只允许 P2/P3 遗留"
        all_pass = sum(1 for a in acc if a.get("status") == "passed")
        pass_rate = all_pass / len(acc)
        if pass_rate < 0.8:
            return f"验收通过率 {all_pass}/{len(acc)} = {int(pass_rate*100)}% < 80%，整体验收未达标不能进入 shipped"
    if current == "shipped" and target == "measured":
        met = [m for m in state.get("metrics", []) if m.get("result") not in (None, "")]
        total_met = len(state.get("metrics", []))
        if not state.get("metrics"):
            return "metrics 为空，至少登记 1 个可观测指标才能推进 measured"
        # codex P2-4：文档写 ceil(总数/3) 所以用 math.ceil，不能用 // 3(floor)
        # 3指标→至少1；4指标→至少2；5指标→至少2（与原floor 5//3=1不同）
        import math
        need = max(1, math.ceil(total_met / 3))
        if len(met) < need:
            return f"metrics 有结果 {len(met)}/{total_met}，至少 ceil({total_met}/3)={need} 个指标有实采值才能进入 measured"
    if current == "measured" and target == "closed":
        dec = state.get("decisions", [])
        if not dec:
            return "measured → closed 前必须先记录一条 D-xxx 决策（continue / iterate / stop 三选一）"
        last = dec[-1]
        if last.get("choice") not in ("continue", "iterate", "stop"):
            return f"最后一条决策 choice={last.get('choice')!r}，必须是 continue/iterate/stop 三个合法值才能 closed"
        # codex P2-4：decision文本不能是空格，同时必须有数据引用 basis_ids 至少1个（否则"有文字就行"=没拿数据拍脑袋）
        dec_txt = str(last.get("decision", "")).strip()
        if not dec_txt:
            return "最后一条决策 decision 文本为空，必须写明结论和数据依据才能 closed"
        basis_raw = [x for x in last.get("basis_ids", []) if str(x).strip()]
        if not basis_raw:
            return "最后一条决策 basis_ids 为空，必须至少挂 1 个 M-xxx / D-xxx / Q-xxx / A-xxx / R-xxx / SRC-xxx 数据引用 ID，证明不是空口拍决策"
        # codex P2-3：basis_ids 的真实性检查——前缀对得上的必须在对应表里存在，挂不存在的ID=蒙混过关
        valid_sets: dict[str, set] = {
            "M": {m.get("id") for m in state.get("metrics", []) if m.get("id")},
            "D": {d.get("id") for d in state.get("decisions", []) if d.get("id")},
            "Q": {q.get("id") for q in state.get("open_questions", []) if q.get("id")},
            "SRC": {s.get("id") for s in state.get("sources", []) if s.get("id")},
            "A": {a.get("id") for a in state.get("acceptance", []) if a.get("id")},
            "R": {r.get("id") for r in state.get("requirements", []) if r.get("id")},
        }
        bad_ids: list[str] = []
        for bid in basis_raw:
            prefixes = ("SRC", "M", "D", "Q", "A", "R")
            matched_prefix = next((p for p in prefixes if bid.upper().startswith(p + "-")), None)
            if matched_prefix is None:
                bad_ids.append(f"{bid}(不合法前缀，需SRC-/M-/D-/Q-/A-/R-之一)")
                continue
            # M类指标必须有result——拿空指标数据来证明决策纯属扯淡
            if bid not in valid_sets.get(matched_prefix, set()):
                bad_ids.append(f"{bid}(对应{matched_prefix}类中不存在此ID)")
                continue
            if matched_prefix == "M":
                real_m = next((m for m in state["metrics"] if m.get("id") == bid), None)
                if real_m and real_m.get("result") in (None, ""):
                    bad_ids.append(f"{bid}(M类无result实采值，不能作为决策依据)")
        if bad_ids:
            return "最后一条决策 basis_ids 真实性未通过：" + "；".join(bad_ids) + "。引用的ID必须存在，M类还必须有实采结果。"
    return ""


def _add_decision(state: dict, decision: str, basis_ids: list[str], choice: str,
                  next_action: Optional[str], decided_by: str) -> None:
    existing = state.get("decisions", [])
    nid = len(existing) + 1
    existing.append({
        "id": f"D-{nid:03d}",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "choice": choice,
        "decision": decision,
        "basis_ids": basis_ids,
        "next_action": next_action or "",
        "decided_by": decided_by or "产品团队",
    })
    state["decisions"] = existing


def _parse_prd_html_acceptance(prd_path: Path):
    from html.parser import HTMLParser

    rows = []

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            # codex P1-1：用正向「进入了带acceptance-table class的table」作为严格判断
            # 不能再用「没有data-preview」反向排除——overview/version-tracking表也可能无data-preview但有R-ID
            self._accept_tbl_depth = 0
            self._tbl_stack: list[set] = []  # 每层嵌套<table>的class集合
            self._in_tr = False
            self._in_td = False
            self._cur_rid = None
            self._cur_aid = None
            self._cur_cells = []
            self._buf = ""

        def handle_starttag(self, tag, attrs):
            attrs_d = dict(attrs)
            if tag == "table":
                classes = set((attrs_d.get("class") or "").split())
                self._tbl_stack.append(classes)
                if "acceptance-table" in classes:
                    self._accept_tbl_depth += 1
            if tag == "tr" and self._accept_tbl_depth > 0:
                # codex P1-1：必须在acceptance-table内，且必带R-ID；优先抓明确写了A-ID的行
                rid_raw = attrs_d.get("data-requirement-id") or ""
                is_rid = rid_raw.startswith("R-")
                if is_rid:
                    self._in_tr = True
                    self._cur_rid = rid_raw
                    self._cur_aid = attrs_d.get("data-acceptance-id") or None
                    self._cur_cells = []
            if tag == "td" and self._in_tr:
                self._in_td = True
                self._buf = ""

        def handle_endtag(self, tag):
            if tag == "table" and self._tbl_stack:
                popped = self._tbl_stack.pop()
                if "acceptance-table" in popped:
                    self._accept_tbl_depth -= 1
            if tag == "tr" and self._in_tr:
                if len(self._cur_cells) >= 3 and self._cur_rid:
                    # codex P1-1：最后两列永远是 scenario + expected_result
                    scenario = self._cur_cells[-2].strip()
                    exp_res = self._cur_cells[-1].strip()
                    rows.append((self._cur_aid, self._cur_rid, scenario, exp_res))
                self._in_tr = False
                self._cur_rid = None
                self._cur_aid = None
            if tag == "td" and self._in_td:
                self._cur_cells.append(self._buf)
                self._in_td = False

        def handle_data(self, data):
            if self._in_td:
                self._buf += data

    content = prd_path.read_text(encoding="utf-8")
    _P().feed(content)
    if not rows:
        raise ValueError(
            "PRD 中没有找到验收条件表行。"
            "验收表必须用 class='acceptance-table' 的 <table> 包裹，"
            "每tbody行必须写 data-requirement-id='R-xxx'，同一R多A时加 data-acceptance-id='A-xxx'。"
        )
    return rows


def _sync_acceptance_from_prd(state: dict, prd_path: Path) -> int:
    parsed_rows = _parse_prd_html_acceptance(prd_path)
    r_ids = {r["id"] for r in state.get("requirements", [])}
    acceptances = state.setdefault("acceptance", [])

    aid_to_a = {a["id"]: a for a in acceptances if a.get("id")}
    from collections import defaultdict
    rid_to_many: dict[str, list[dict]] = defaultdict(list)
    for a in acceptances:
        rid = a.get("requirement_id")
        if rid:
            rid_to_many[rid].append(a)
    updated = 0
    missing_aids: list[str] = []

    for aid, rid, scenario, exp_res in parsed_rows:
        if rid not in r_ids:
            raise ValueError(f"PRD 行 {rid}（A={aid}）在 requirements[] 中不存在，先补 R 再写 A")
        if not scenario or not exp_res:
            raise ValueError(f"PRD 行 {rid}（A={aid}）scenario / expected_result 为空，不允许写空")

        # codex P1-2：PRD 行显式写了 data-acceptance-id=xxx 时，必须 100% 严格匹配：
        #   (1) 该 A-xxx 必须在档案 acceptance[] 存在；(2) A-xxx.requirement_id 必须 == PRD行的R-ID
        # 不满足直接抛错停止同步，绝不回退匹配，防止写错 ID 静默覆盖正确验收
        target = None
        if aid:
            explicit_a = aid_to_a.get(aid)
            if explicit_a is None:
                raise ValueError(
                    f"PRD 验收行显式写了 data-acceptance-id='{aid}'，但需求档案 acceptance[] 中找不到 ID='{aid}'。"
                    f"要么在 acceptance[] 先补 {aid}，要么把 PRD 里的 A-ID 改对。写错 A-ID 会静默覆盖别的验收，**禁止回退匹配**。"
                    f"上下文：行 R={rid} scenario='{scenario[:30]}…'"
                )
            if explicit_a.get("requirement_id") != rid:
                raise ValueError(
                    f"PRD 验收行 data-acceptance-id='{aid}' 的 requirement_id={explicit_a.get('requirement_id')!r}，"
                    f"与 PRD 行 data-requirement-id='{rid}' 不一致。"
                    f"A-xxx 必须归属于正确的 R-xxx，禁止张冠李戴。"
                )
            target = explicit_a
        else:
            # PRD行没写A-ID（1R对应唯一A的简单情况）→ 允许用scenario模糊匹配
            candidates = rid_to_many.get(rid, [])
            for cand in candidates:
                if cand.get("scenario") and cand["scenario"].strip() == scenario:
                    target = cand
                    break
            if target is None and len(candidates) == 1:
                target = candidates[0]
        if target is None:
            hint = aid or f"R={rid} scenario={scenario[:12]}…"
            missing_aids.append(hint)
            continue

        target["requirement_id"] = rid
        old_cat = f"{target.get('scenario','')}|{target.get('expected_result','')}"
        new_cat = f"{scenario}|{exp_res}"
        target["scenario"] = scenario
        target["expected_result"] = exp_res
        # codex P1-1：如果scenario或expected发生变化，原来的passed结论已经不成立——
        # status从passed/failed重置为pending，checked_at/evidence_ref清空，必须重新验收
        if old_cat != new_cat and target.get("status") in ("passed", "failed"):
            target["status"] = "pending"
            target["checked_at"] = None
            target["evidence_ref"] = None
        concat = scenario + exp_res
        if any(k in concat for k in ("权限", "未接入", "未配置", "部分完成", "结果未知", "超时", "错误", "兜底", "冲突")):
            target["category"] = "边界异常"
        elif any(k in concat for k in ("目录", "版本", "发布", "暂停", "Prompt", "配置", "治理")):
            target["category"] = "平台配置"
        else:
            target["category"] = "核心流程"
        if any(k in concat for k in ("不调用写入", "不宣称成功", "不进入提交", "不得", "禁止",
                                      "真实业务回执", "单据号", "业务记录ID")):
            target["priority"] = "P0"
        elif target["category"] == "边界异常" and any(k in concat for k in ("未配置", "权限不足", "未接入")):
            target["priority"] = "P0"
        else:
            target["priority"] = "P1"
        updated += 1

    if missing_aids:
        raise ValueError(
            "PRD 有 " + str(len(missing_aids)) + " 行找不到对应 A-xxx。"
            "同一 R 有多个 A 时请在 PRD 行上写 data-acceptance-id='A-xxx'，"
            "或先补 A-xxx 到 acceptance[]。未匹配：" + ", ".join(missing_aids[:6])
        )
    if updated != len(parsed_rows):
        raise ValueError(
            f"更新数 {updated} ≠ PRD 验收行数 {len(parsed_rows)}，请检查 A-xxx ID 是否对齐。"
        )
    return updated


# =========================================================
# -- 审计
# =========================================================

def audit(state: dict) -> list[str]:
    errs = []
    s_ids = {s["id"] for s in state.get("sources", [])}
    r_ids = {r["id"] for r in state.get("requirements", [])}
    m_ids = {m["id"] for m in state.get("metrics", [])}
    a_ids = {a["id"] for a in state.get("acceptance", [])}

    for r in state.get("requirements", []):
        for sid in r.get("source_ids", []):
            if sid not in s_ids:
                errs.append(f"REF-001：R {r['id']}.source_ids 引用不存在的 {sid}")
        for mid in r.get("metric_ids", []):
            if mid not in m_ids:
                errs.append(f"REF-002：R {r['id']}.metric_ids 引用不存在的 {mid}")
        for aid in r.get("acceptance_ids", []):
            if aid not in a_ids:
                errs.append(f"REF-003：R {r['id']}.acceptance_ids 引用不存在的 {aid}")
    for a in state.get("acceptance", []):
        if a.get("requirement_id") not in r_ids:
            errs.append(f"REF-004：A {a['id']}.requirement_id={a.get('requirement_id')} 不存在")
    for a in state.get("acceptance", []):
        missing = [k for k in ("scenario", "expected_result", "category", "priority") if not a.get(k)]
        if missing:
            errs.append(f"ACC-001：A {a['id']} 缺字段 {missing}（7.1 同步后应全部填充）")
    stage = state.get("stage", "discovery")
    if stage == "measured" and all(m.get("result") in (None, "") for m in state.get("metrics", [])):
        errs.append("STAGE-001：stage=measured 但所有 metrics.result 为空，违反无真实数据不标 measured 规则")
    for q in state.get("open_questions", []):
        if not q.get("owner") or "待定" in q.get("owner", ""):
            errs.append(f"OQ-001：Q {q.get('id')} owner 仍是「待定」，真实推进需指定到人")
    for m in state.get("metrics", []):
        if not m.get("baseline_plan"):
            errs.append(f"METRIC-001：M {m['id']} 缺 baseline_plan（每个指标都要有怎么拿基线的路径）")
    # AI类需求：必须有 hallucination_rate / escalation_rate / avg_confidence 三个品质指标至少之一
    tags = set(t.lower() for t in state.get("tags", []) if isinstance(t, str))
    art = state.get("artifacts", {}) if isinstance(state.get("artifacts"), dict) else {}
    # 启发式判断：tags 里出现AI类关键词 / metrics名里出现AI类 / artifacts里登记了ai_ethics_review
    title_tokens = {w.lower() for w in re.split(r'\W+', state.get("title", "")) if w}
    ai_signals = tags & {"agent", "llm", "ai", "大模型", "智能", "prompt", "rag", "gpt", "模型", "智能体"}
    ai_signals = ai_signals or (
        any(k in (str(v) or "") for k, v in art.items() if k in ("ai_ethics_review",))
    ) or any(k in " ".join(m.get("name", "") for m in state.get("metrics", [])).lower()
             for k in ("hallucination", "escalation", "avg_confidence", "低置信", "置信度", "幻觉"))
    # 如果 title 里含明确关键词也算
    ai_signals = ai_signals or any(k in str(state.get("title", "")).lower()
                                   for k in ("agent", "大模型", "智能体", "prompt", "rag", "gpt", "llm"))
    if ai_signals:
        m_names = " ".join(str(m.get("name", "")) + " " + str(m.get("id", "")) for m in state.get("metrics", []))
        m_names_lower = m_names.lower()
        quality_metrics = sum(
            1 for token in ("hallucination", "escalation", "avg_confidence", "幻觉", "置信度", "升级人工", "升级率")
            if token in m_names_lower
        )
        if quality_metrics < 1:
            errs.append(
                "AIMETRIC-001：检测到这是AI类需求（title/tags/artifacts 命中AI关键词），"
                "但 metrics[] 里没有 hallucination_rate / escalation_rate / avg_confidence 三类品质指标的至少之一。"
                "AI产品没有品质指标=盲人开车，必须加至少一个。"
            )
        # AIMETRIC-002：有RAG就必须有 retrieval_hit_rate / retrieval_recall 至少之一（可选）
        # 如果 PRD 的 artifacts.prd 里出现 RAG 关键词，再加 AIMETRIC-002
    # AIETHIC-001：AI类需求 + stage ≥ ready → artifacts.ai_ethics_review 必须存在
    if ai_signals and STAGE_ORDER.index(state.get("stage", "discovery")) >= STAGE_ORDER.index("ready"):
        review_path = art.get("ai_ethics_review")
        record_dir = state.get("__record_dir__")
        exists = False
        if review_path and isinstance(record_dir, Path):
            exists = (record_dir / review_path).is_file()
        if not exists:
            errs.append(
                "AIETHIC-001：AI类需求 stage ≥ ready，必须先跑完 edu-pm-ai-ethics 子工作流并在 "
                "artifacts.ai_ethics_review 登记 AI伦理审查.html 路径。否则上线出了合规问题没人背。"
                "如果这不是AI类需求，请去掉 title/tags 里的 AI 关键词即可豁免。"
            )

    # ---- 沟通记录单向真相源检查 ----
    record_dir = state.get("__record_dir__", None) if isinstance(state.get("__record_dir__"), Path) else None
    if record_dir:
        comm_log = record_dir / "沟通记录.md"
        if comm_log.is_file():
            try:
                comm_txt = comm_log.read_text(encoding="utf-8")
            except OSError:
                comm_txt = ""
            # TRUTH-001：沟通记录出现形如「1. xxx 待确认 / (1) xxx Owner=... / ① xxx 待核对」的编号式待确认清单，
            # 或出现在 ## 待确认 / ## 待后续确认 / ## 未解决 等标题下的编号条目。
            in_confirm_block = False
            bad_lines: list[str] = []
            confirm_block_headings = ("待确认", "待后续确认", "待核对", "待提供", "未解决", "待确定", "待补", "open questions")
            numbering_re = re.compile(r'^\s*(?:\d{1,2}\s*[、.．)]|[①-⑳]|\(\d{1,2}\)|[（(]\d{1,2}[）)])\s*')
            for raw in comm_txt.splitlines():
                stripped = raw.strip()
                # 标题切换
                if stripped.startswith("#"):
                    heading = stripped.lstrip("#").strip()
                    in_confirm_block = any(k.lower() in heading.lower() for k in confirm_block_headings)
                    continue
                if not stripped or len(stripped) > 300:
                    continue
                numbered = numbering_re.match(stripped)
                tail = stripped[numbered.end():] if numbered else stripped
                # 触发条件 1：明确写了「待确认/待核对/Owner=」等关键词
                clue_hit = any(k in tail for k in (
                    "待确认", "待核对", "待提供", "待补充", "待补齐", "待确定", "待定",
                    "Owner=", "Owner：", "owner=", "owner：", "负责人=", "负责人："))
                # 触发条件 2：出现在「待确认/未解决」类 heading 下的编号条目（不管有没有关键词）
                if in_confirm_block and numbered:
                    bad_lines.append(tail[:80])
                elif numbered and clue_hit:
                    bad_lines.append(tail[:80])
            for bad in bad_lines:
                errs.append(f"TRUTH-001：沟通记录存在编号式待确认项「{bad}」，请挪入需求档案.open_questions[]（单向真相源）")
    return errs


# =========================================================
# -- CLI
# =========================================================

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--project", default=".", help="已安装 PM Forge 的项目目录")
    parser.add_argument("--name", required=True, help="需求名称；同一需求重复调用会返回已有档案")
    parser.add_argument("--requirement-dir", help="已有需求目录相对项目的位置；独立单需求项目可用 .")

    parser.add_argument("--update", action="store_true", help="启用更新模式（否则是创建/定位模式）")
    parser.add_argument("--push-stage", choices=STAGE_ORDER, help="推进到指定 stage（需满足对应前置条件）")
    parser.add_argument("--add-decision", help="追加一条决策记录的摘要文案")
    parser.add_argument("--basis-ids", default="", help="逗号分隔的 SRC-xxx/R-xxx，作为决策依据")
    parser.add_argument("--choice", choices=sorted(VALID_CHOICES), default="continue",
                        help="决策的 choice 字段")
    parser.add_argument("--next-action", help="决策后的后续动作一句话")
    parser.add_argument("--decided-by", default="产品团队", help="决策人/决策团队")
    parser.add_argument("--sync-acceptance-from-prd",
                        help="从 PRD HTML 同步验收（路径相对需求目录）")
    parser.add_argument("--audit", action="store_true", help="只读审计需求档案的跨字段一致性")
    args = parser.parse_args()

    project = Path(args.project)
    try:
        record_path = initialize(project, args.name, args.requirement_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"无法创建/定位需求档案：{error}\n")

    if not args.update and not args.audit:
        print(record_path)
        return 0

    state = _load_record(record_path)
    state["__record_dir__"] = record_path.parent  # 仅在内存里用，不落盘

    if args.audit:
        errs = audit(state)
        if errs:
            print("AUDIT FAIL  " + str(record_path))
            for e in errs:
                print("      ❌ " + e)
            print(f"\n共 {len(errs)} 条问题。")
            return 1
        print("AUDIT PASS  " + str(record_path))
        print("      📋 引用一致性 OK；stage 规则 OK；A-xxx 字段完整；metrics.baseline_plan 全填")
        return 0

    working = copy.deepcopy(state)
    changed = False

    # 先把本次所有输入应用到候选状态，再检查 stage 的最终状态。
    # 这样关闭阶段校验看到的是本次 --add-decision / PRD 同步后的数据，
    # 失败时只丢弃候选对象，磁盘上的需求档案保持原样。
    if args.add_decision:
        basis = [s.strip() for s in args.basis_ids.split(",") if s.strip()]
        _add_decision(working, args.add_decision, basis, args.choice, args.next_action, args.decided_by)
        changed = True
        print(f"[decision] 新增 D-{len(working['decisions']):03d}（{args.decided_by}）")

    if args.sync_acceptance_from_prd:
        prd_path = (record_path.parent / args.sync_acceptance_from_prd).resolve()
        if not prd_path.is_file():
            parser.exit(1, f"PRD HTML 不存在：{prd_path}\n")
        try:
            n = _sync_acceptance_from_prd(working, prd_path)
        except ValueError as exc:
            parser.exit(1, f"SYNC ACCEPTANCE BLOCK：{exc}\n")
        changed = True
        counts = {"P0": 0, "P1": 0}
        cats: dict[str, int] = {}
        for a in working.get("acceptance", []):
            counts[a.get("priority", "P?")] = counts.get(a.get("priority", "P?"), 0) + 1
            cats[a.get("category", "?")] = cats.get(a.get("category", "?"), 0) + 1
        print(f"[acceptance] 从 PRD 同步更新 {n} 条 A-xxx：P0={counts.get('P0',0)} P1={counts.get('P1',0)}；分类 {cats}")

    if args.push_stage:
        old_stage = state.get("stage", "discovery")
        if old_stage == "measured" and args.push_stage == "closed" and not args.add_decision:
            parser.exit(1, "STAGE BLOCK：measured → closed 必须通过 --add-decision 提供明确决策及数据依据\n")
        reason = _check_stage_push(old_stage, args.push_stage, working)
        if reason:
            parser.exit(1, f"STAGE BLOCK：{reason}\n")
        working["stage"] = args.push_stage
        changed = True
        print(f"[stage] {old_stage} → {args.push_stage}（最终状态校验通过）")
        if not args.add_decision:
            auto = (f"stage 自动推进：{old_stage} → {args.push_stage}，"
                    f"基于：open_questions={len(working.get('open_questions',[]))}；"
                    f"artifacts 已登记 {len(working.get('artifacts',{}))} 件")
            _add_decision(working, auto, [], args.choice, args.next_action, args.decided_by)
            print(f"[decision] 自动新增 D-{len(working['decisions']):03d}（stage 推进记录）")

    if changed:
        errs = audit(working)
        if errs:
            parser.exit(1, "落盘前 AUDIT 失败，本次更新未写入，请先修复：\n  · " +
                        "\n  · ".join(errs) + "\n")
        working.pop("__record_dir__", None)
        _save_record(record_path, working)
        print(f"[saved] {record_path}")
    else:
        print("（--update 模式下没有传 --push-stage / --add-decision / --sync-acceptance-from-prd，没做任何改动）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
