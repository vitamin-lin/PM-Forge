#!/usr/bin/env python3
"""PRD 格式校验（v2.9 工作流 §5.2 的第一步）。

用法：
    python3 validate_prd.py [需求名/需求文档/需求名-PRD.html ...]
    py -3 validate_prd.py …            # Windows 上没有 python3 命令

不带参数时，从当前目录向下查找所有 *-PRD.html 逐个校验。
退出码 0 = 全部通过；1 = 有文件未通过；2 = 没找到文件。

校验的是「机械可判定」的部分：章节独立性、固定表头与列数、
埋点命名、描述列分块与逐条换行、data-preview 覆盖、
文档级 style 位置、章节编号连续性。
视觉类检查（遮挡、字号、配色统一）仍需人工按 §4.3 / §4.6 核对。
"""
import sys
import re
from pathlib import Path
from html.parser import HTMLParser
from pm_requirement import artifact_root

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}

CORE_SECTIONS = ["项目信息", "版本记录", "需求背景", "需求目标", "详细方案"]

SCHEMAS = {
    "version-table":  ["版本", "日期", "修订人", "修订说明"],
    "scheme-table":   ["一级模块", "二级功能", "原型", "描述"],
    "overview-table": ["模块", "一级功能", "说明"],
    "tracking-table": ["序号", "埋点名", "埋点中文名", "埋点类型", "埋点参数", "参数值"],
}

CN_NUM = "一二三四五六七八九十"


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def text(self):
        return "".join(x.text() if isinstance(x, Node) else x for x in self.children)

    def find(self, tag=None, css_class=None):
        result = []
        for child in self.children:
            if not isinstance(child, Node):
                continue
            if (tag is None or child.tag == tag) and (
                css_class is None or css_class in child.attrs.get("class", "").split()
            ):
                result.append(child)
            result.extend(child.find(tag, css_class))
        return result

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.current = self.root
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent and node.tag != tag:
            node = node.parent
        if node.parent:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def _section_of(root):
    """Return a function mapping a node to the nearest preceding h2/h3 heading text."""
    heads = [(n, n.text().strip()) for n in root.walk() if n.tag in ("h2", "h3")]

    def lookup(node):
        found = ""
        for n, txt in heads:
            if n is node:
                break
            if n.tag == "h2":
                found = txt
        return found

    return lookup


def validate_prd(content):
    root = Tree(content).root
    h2 = [n.text().strip() for n in root.find("h2")]
    errors = []
    warnings = []

    # ---- 1. 核心章节与独立性 ----
    for name in CORE_SECTIONS:
        if not any(h.endswith(name) for h in h2):
            errors.append("缺少独立章节：" + name)
    if any("项目信息" in h and "版本记录" in h for h in h2):
        errors.append("项目信息和版本记录必须分开成两张表/两个章节")
    if any(("边界" in h or "异常处理" in h) for h in h2):
        errors.append("不设独立的异常/边界章节；边界情况写进详细方案描述列的【边界说明】")

    # ---- 2. 章节编号连续性 ----
    numbered = []
    for h in h2:
        m = re.match(r"^([一二三四五六七八九十]+)、", h)
        if m:
            numbered.append((m.group(1), h))
    expected = list(CN_NUM[: len(numbered)])
    actual = [n for n, _ in numbered]
    if actual and actual != expected:
        errors.append("章节编号不连续（应从 一 开始顺排）：实际为 " + "、".join(actual))

    # ---- 3. 固定表头与列数 ----
    for css, expect in SCHEMAS.items():
        tables = root.find("table", css)
        required = css in {"version-table", "scheme-table"} or any(
            ("数据埋点" in h if css == "tracking-table"
             else "需求概述" in h if css == "overview-table" else False)
            for h in h2
        )
        if required and not tables:
            errors.append("缺少规范表格：" + css)
        for table in tables:
            rows = table.find("tr")
            if not rows:
                errors.append(css + " 没有表头行")
                continue
            heads = [c.text().strip() for c in rows[0].children
                     if isinstance(c, Node) and c.tag == "th"]
            if heads != expect:
                errors.append(css + " 表头必须为：" + "、".join(expect) + "（实际：" + "、".join(heads) + "）")

    # ---- 4. 项目信息必须独立双列表 ----
    meta = root.find("table", "meta-table")
    if not meta:
        errors.append("项目信息应使用独立 meta-table")
    else:
        for table in meta:
            for row in table.find("tr"):
                cells = [c for c in row.children if isinstance(c, Node) and c.tag in ("td", "th")]
                if len(cells) != 2:
                    errors.append("项目信息应为双列（字段 | 值）")
                    break

    # ---- 5. 详细方案：data-preview / 原型列 / 描述列 ----
    for table in root.find("table", "scheme-table"):
        rows = table.find("tr")
        for row in rows[1:]:
            cells = [c for c in row.children if isinstance(c, Node) and c.tag == "td"]
            if not cells:
                continue
            if "data-preview" not in row.attrs:
                errors.append("详细方案每行必须带 data-preview（供双栏滚动联动）")
            if len(cells) >= 3:
                proto = cells[-2]
                has_media = bool(proto.find("img") or proto.find("iframe"))
                if not has_media:
                    errors.append("原型列必须有内容（img.proto-shot 或可交互 iframe）")
            if "desc" not in cells[-1].attrs.get("class", "").split():
                errors.append("功能行末列应为 desc 描述单元格")
        for cell in table.find("td", "desc"):
            text = cell.text()
            if not all(label in text for label in ("【页面元素】", "【交互说明】")):
                errors.append("每个描述单元格必须包含【页面元素】和【交互说明】")
            if not cell.find(css_class="desc-block"):
                errors.append("描述应使用 desc-block 分块并逐条换行（不要用 <br> 硬换行）")
            for block in cell.find(css_class="desc-block"):
                items = [n for n in block.children
                         if isinstance(n, Node) and n.tag in ("p", "ol", "ul")]
                if not items:
                    errors.append("描述分块需要独立段落或列表")
            for line in cell.find("p") + cell.find("li"):
                if len(re.findall(r"(?:^|\s|[；;])\d+[、．.]", line.text())) > 1:
                    errors.append("每个元素或交互必须独立成段（多个编号不能挤在一句里）")
            if cell.find("br"):
                errors.append("描述列不要用 <br> 硬换行，改用独立 <p>")

    # ---- 6. 埋点命名与列数 ----
    for table in root.find("table", "tracking-table"):
        rows = table.find("tr")
        for row in rows[1:]:
            cells = [c for c in row.children if isinstance(c, Node) and c.tag == "td"]
            if not cells:
                continue
            if len(cells) != 6:
                errors.append("埋点表每行必须有六列（缺的格写「待确认（用户提供参考）」，不要留空）")
                continue
            event = cells[1].text().strip()
            if not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", event) or len(event) > 48:
                errors.append("埋点名需要简短英文 snake_case：" + event)

    # ---- 7. 文档级 style 必须在 #prdContent 内（一键复制全文才带得走样式）----
    # 只做"存在性"判定：<head> 放公共骨架样式、正文样式放 <main> 内是正常分工，
    # 但 #prdContent 内必须至少有一份正文样式，否则复制出去的正文会掉格式。
    main_nodes = [m for m in root.find("main") if m.attrs.get("id") == "prdContent"]
    if not main_nodes:
        errors.append("缺少 <main id=\"prdContent\"> 正文容器")
    elif not any(m.find("style") for m in main_nodes):
        errors.append("#prdContent 内没有正文 <style>；一键复制全文会丢掉正文排版样式")

    # ---- 8. 需求目标不应是任务清单 ----
    goal_tables = root.find("table", "goal-table")
    for tbl in goal_tables:
        rows = tbl.find("tr")
        heads = [c.text().strip() for c in rows[0].children
                 if isinstance(c, Node) and c.tag == "th"] if rows else []
        if heads != ["用户结果", "衡量指标", "统计口径", "预期方向", "目标值"]:
            errors.append("goal-table 表头必须为：用户结果、衡量指标、统计口径、预期方向、目标值")

    # ---- 9. BLOCK-001：需求概述含疑似单页细节未下沉（逐字段映射表/逐状态用户可见内容） ----
    section_of = _section_of(root)
    for h3 in root.find("h3"):
        section_title = h3.text().strip()
        if not any(k in section_title for k in ("纵向样板", "字段映射", "用户可见", "办理链路", "状态")):
            continue
        # 找这个h3之后到下一个h3/h2之间的所有table tr文本
        bucket = []
        cursor = h3
        while True:
            cursor = cursor.parent and next(
                (s for s in cursor.parent.children[cursor.parent.children.index(cursor)+1:]
                 if isinstance(s, Node)), None
            ) if hasattr(h3, "parent") and h3.parent else None
            if not cursor:
                break
            if cursor.tag in ("h3", "h2"):
                break
            if cursor.tag == "table":
                for tr in cursor.find("tr"):
                    tds = [c.text().strip() for c in tr.children if isinstance(c, Node) and c.tag == "td"]
                    if not tds:
                        continue
                    bucket.append("｜".join(tds))
            else:
                bucket.append(cursor.text())
        text_block = "\n".join(bucket)
        # 逐字段映射表（典型标签B）：出现表单字段名且含"候选/来源/推断/未验证"
        field_keywords = ("费用类型", "发生日期", "金额", "币种", "事由", "发票", "附件",
                          "计划名称", "描述", "时间", "重复", "老师", "学生", "科目",
                          "授课方式", "教学模式", "地点", "课室", "提醒")
        field_matches = sum(1 for k in field_keywords if k in text_block)
        if field_matches >= 4:
            errors.append(
                "BLOCK-001：需求概述「" + section_title + "」疑似包含逐字段映射表（命中"
                + str(field_matches) + "个字段关键词），属于单页专属细节（标签B），"
                "应下沉到详细方案 scheme-table 对应行的描述列；需求概述本节只保留"
                "「详见详细方案6.x.x」一行占位引用，跨页共享规则（标签A）才留在此处。"
            )
        # 逐状态用户可见内容+系统转移（典型标签B）
        step_keywords = ("路由候选", "可用性闸口", "提取与补问", "草稿预览",
                         "明确确认", "执行与核实", "暂停与续办", "用户可见内容",
                         "系统判断与转移条件", "提取与补问", "结果待核实")
        step_matches = sum(1 for k in step_keywords if k in text_block)
        if step_matches >= 3 and field_matches < 4:
            errors.append(
                "BLOCK-001：需求概述「" + section_title + "」疑似包含逐状态的用户可见"
                "内容/转移条件（命中" + str(step_matches) + "个状态关键词），属于单页"
                "专属细节（标签B），应拆成多行进入详细方案scheme-table，每行对应一个"
                "状态；需求概述本节只保留跨页共享规则（标签A）+ 占位引用。"
            )

    # ---- 10. BLOCK-003：必填「风险与应对」卡片少于3条或仍含模板话术 ----
    risk_cards = []
    for div in root.find("div"):
        cls = div.attrs.get("class", "")
        if "risk-card" in cls and "required-block" in cls:
            risk_cards.append(div)
    if not risk_cards:
        # 旧版骨架没有required-block时，尝试找原文案写的risk-card，若内容写的是"本期不做什么"也不算真正的风险卡
        for div in root.find("div", "risk-card"):
            first_b = div.find("b")
            if first_b and "不做" in first_b[0].text() if first_b else False:
                continue
            risk_cards.append(div)
    if risk_cards:
        for rc in risk_cards:
            total_li = rc.find("li")
            valid = [li for li in total_li if "请填" not in li.text()]
            if len(valid) < 3:
                errors.append(
                    "BLOCK-003：「风险与应对」是必填块，至少写3条和当前项目强相关的真实"
                    "风险（不能写『进度风险』这种空泛模板，要写触发条件+应对方案+Owner）。"
                    "当前只识别到" + str(len(valid)) + "条有效。"
                )
    # 另外校验：scope-card后必须紧跟out-of-scope-card（或旧risk-card但内容写不做），再紧跟真正的风险卡
    scope_divs = root.find("div", "scope-card")
    if scope_divs:
        scope_parent = scope_divs[0].parent
        if scope_parent:
            idx_scope = scope_parent.children.index(scope_divs[0])
            has_out = False
            has_real_risk = False
            for sib in scope_parent.children[idx_scope + 1:idx_scope + 6]:
                if isinstance(sib, Node) and sib.tag == "div":
                    cls = sib.attrs.get("class", "")
                    fb = sib.find("b")
                    fb_txt = fb[0].text() if fb else ""
                    if "out-of-scope-card" in cls or ("risk-card" in cls and "不做" in fb_txt):
                        has_out = True
                    elif "risk-card" in cls and "不做" not in fb_txt and ("风险" in fb_txt or "应对" in fb_txt or "⚠️" in fb_txt):
                        has_real_risk = True
            if scope_divs and not (has_out and has_real_risk):
                errors.append(
                    "BLOCK-003：需求概述需要3张独立卡片：本期范围(scope-card) → 本期不做什么"
                    "(out-of-scope-card) → 风险与应对(风险+⚠️标题的risk-card)。当前缺少真正的"
                    "『风险与应对』独立块。旧骨架把『本期不做什么』误用了risk-card类名，会和"
                    "真正的风险块视觉混淆，请升级骨架模板用out-of-scope-card区分。"
                )

    # §11 BLOCK-004：AI产品PRD强制骨架必填AI-1~AI-4 四块（QAPractices AI Testing Checklist 硬性检查）
    # 触发条件：PRD 全局文本中出现 AI 类关键词 ≥3 次
    AI_KEYWORDS = ("agent", "llm", "大模型", "prompt", "rag", "gpt", "幻觉",
                   "模型调用", "模型版本", "置信度", "embedding", "向量库",
                   "人工复核", "低置信度", "token预算")

    def _has_ai_intent(text: str) -> bool:
        lowered = text.lower()
        return sum(1 for kw in AI_KEYWORDS if kw.lower() in lowered) >= 3

    has_ai = _has_ai_intent(content)

    if has_ai:
        ai_card_specs = [
            ("ai-boundary-card",      "【AI-1 模型选型】"),
            ("ai-hallucination-card", "【AI-2 幻觉兜底】"),
            ("ai-safety-card",        "【AI-3 注入防护&PII】"),
            ("ai-eval-card",          "【AI-4 评测方案】"),
        ]
        missing_cards: list[str] = []
        card_refs: dict[str, Node] = {}
        for cls_name, label in ai_card_specs:
            found = root.find("div", cls_name)
            if not found:
                missing_cards.append(label)
            else:
                card_refs[cls_name] = found[0]
        if missing_cards:
            errors.append(
                "BLOCK-004：检测到这是AI产品PRD（出现LLM/Prompt/RAG/Agent等关键词 ≥3 次），"
                "但缺失AI专属必填块：缺 " + " / ".join(missing_cards) + "。"
                "必须补齐四块（模板里有AI-1~AI-4，位置在详细方案后）。"
                "普通SaaS产品：把AI类关键词删掉即可豁免此检查。"
            )
        # 幻觉卡：至少出现「置信度 / confidence」和「拒绝话术 / 人工 / HITL」
        halluc = card_refs.get("ai-hallucination-card")
        if halluc is not None:
            txt = halluc.text()
            if ("置信度" not in txt) and ("confidence" not in txt.lower()):
                errors.append(
                    "BLOCK-004：AI-2 幻觉兜底块必须明确写「置信度阈值」（例如 字段级 confidence ≥0.82）。"
                    "没有阈值就无法判断什么时候该走兜底。"
                )
            if not any(k in txt for k in ("拒绝话术", "人工", "HITL", "升级工单", "转人工")):
                errors.append(
                    "BLOCK-004：AI-2 幻觉兜底块必须明确写「信息不足时的拒绝话术/低置信度UI/人工升级路由」三选一至少一个，"
                    "否则「出问题了怎么办」这件事就没闭环。"
                )
        # 评测卡：黄金测试集表至少3个数据行（header不算）
        eval_card = card_refs.get("ai-eval-card")
        if eval_card is not None:
            rows = eval_card.find("tr")
            real = sum(1 for tr in rows if tr.find("td"))
            if real < 3:
                errors.append(
                    "BLOCK-004：AI-4 评测方案至少填3条（黄金测试集条目数×通过率×抽样复审比例）。"
                    "3条以下上线后没有评测基线，属于盲人开车。"
                )

    # §12 WARN-005：业务任务卡（codex P3-1）。R≥5条的大需求建议启用task-card，不阻塞仅提醒
    overview_tbl = root.find("table", "overview-table")
    req_count = 0
    if overview_tbl:
        for tbl in (overview_tbl if isinstance(overview_tbl, list) else [overview_tbl]):
            for tr in tbl.find("tr"):
                if tr.find("td"):
                    req_count += 1
    if req_count >= 5:
        task_div = root.find("div", "task-card")
        task_rows = 0
        if task_div:
            for tdiv in (task_div if isinstance(task_div, list) else [task_div]):
                for tr in tdiv.find("tr"):
                    if tr.find("td"):
                        task_rows += 1
        need = max(1, round(req_count * 0.5))
        if task_rows < need:
            warnings.append(
                f"WARN-005：需求条目数 {req_count} ≥ 5，建议启用 task-card 业务任务卡，至少填 {need} 条。"
                "缺任务卡易出现「功能写了但操作角色/触发条件/异常回退/成功凭证未闭环」。"
            )

    for w in warnings:
        print("⚠️  " + w)
    if errors:
        raise ValueError("PRD 格式检查未通过：\n" + "\n".join(dict.fromkeys(errors)))
    return True


def main(argv):
    if len(argv) > 1:
        files = [Path(p) for p in argv[1:]]
    else:
        # 默认只扫 `[需求名]/需求文档/*-PRD.html`——项目里的历史 PRD / 分享源文件 /
        # 需求挖掘目录下的旧稿不按本规范撰写，扫进来只会制造噪音。
        project = Path.cwd().resolve()
        roots = [project]
        try:
            configured = artifact_root(project)
            if configured != project:
                roots.append(configured)
        except (OSError, ValueError):
            pass  # 仍可显式传入 PRD 路径；这里仅负责默认发现。
        files = sorted({path for root in roots
                        for path in root.glob("*/需求文档/*-PRD.html")})
        if not files:
            files = sorted(Path.cwd().glob("*-PRD.html"))
    if not files:
        print("没有找到 *-PRD.html（可显式传入路径，或在本项目根目录运行）")
        return 2

    failed = 0
    for path in files:
        try:
            validate_prd(path.read_text(encoding="utf-8"))
            print("PASS  " + str(path))
        except ValueError as exc:
            failed += 1
            print("FAIL  " + str(path))
            for line in str(exc).splitlines()[1:]:
                print("      " + line)
        except OSError as exc:
            failed += 1
            print("ERROR " + str(path) + " —— " + str(exc))
    print("\n共 %d 个文件，%d 个未通过。" % (len(files), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
