---
name: edu-pm-workflow
description: "Product management workflow for producing PRDs, interactive HTML prototypes, flowcharts, acceptance checklists, demand analysis, and data reports. Use when the user describes a product requirement, asks for PRD/prototype/flowchart/checklist/data-analysis output, or wants to continue this PM workflow."
---

# PM Workflow Skill

This skill turns product requirements into working artifacts: PRD HTML, interactive prototype HTML, flowchart HTML, acceptance checklist, demand analysis, and data reports. It is designed for product work across different business domains and product types.

## First Decision

1. Identify the **product project** before writing artifacts. The directory containing this Git-tracked skill may only be its source repository; when the user is working on another product, use that product's project root. If the destination is ambiguous, resolve it before creating a requirement folder.
2. If `.agents/workflows/` and required scripts, including `scripts/pm_requirement.py`, already exist in the product project, read the relevant workflow and continue from its current state.
3. If the workflows or required scripts are missing and the task needs their runtime features, install/update this skill in the product project (command below). For editing existing product artifacts without the export service, load the corresponding workflow from this personal skill's `assets/workflows/` and keep the product project free of unnecessary runtime files. Preserve locally customized workflow files; the installer puts proposed updates in `.pm-workflow/updates/` for comparison.
4. If the user explicitly asks to reinstall or update the workflow, run the same command. Runtime scripts are refreshed; files the user has edited are kept and the new version is written to `.pm-workflow/updates/` for comparison. Replaced copies are backed up under `.handoff/skill-backups/`.

Install / update — run `scripts/initialize.py` with the platform's Python. It is the single cross-platform installer; `scripts/init.sh` and `scripts/init.bat` are only thin wrappers around it for users who prefer a double-click.

```bash
# macOS / Linux
python3 <skill-dir>/scripts/initialize.py --project .
```

```bat
rem Windows (py is the official launcher; there is no python3 command)
py -3 <skill-dir>\scripts\initialize.py --project .
```

Locating `<skill-dir>`: use your file-search tool (Glob/Grep) for `**/edu-pm-workflow/scripts/initialize.py` across the project and the user's skill directories (`.agents/skills`, `~/.agents/skills`, `~/.claude/skills`, `~/.cursor/skills`). Do **not** shell out to `find` — on Windows `find` is `System32\find.exe`, a text-search tool that takes entirely different arguments, so the discovery step itself would fail before installation ever starts.

## Workflow Routing

### Step 0 · Context Ingestion Rules（P2-1 自动产品上下文，mySecond 同款设计）

**Before running ANY workflow below**, first try to read 产品项目根目录下 `.pm-product-context/` 里的 3 份文件（全部可选；**读不到就静默跳过，绝不报错**——老项目没有这三份文件也能正常工作）：

1. `.pm-product-context/product.md` → 宪法级共享事实：一句话定位/画像/技术栈/合规红线/已拍板决策/术语表/竞品锚点
2. `.pm-product-context/personas.md` → 用户画像详情版（product.md 里写不下时用）
3. `.pm-product-context/competitors.md`→ 完整竞品分析详情（product.md 里写不下时用）

读完以后以以下话术注入会话最开头（只在本次会话内生效，不写文件）：

> 📥 以下为本项目产品级共享事实，本会话所有需求默认遵守，除非用户显式说明冲突：
>
> 「把每份非空文件的全文原样贴过来」
>
> 若有冲突，以用户本次会话的最新明确指令为准。

**为什么这样做：** 避免每次开新需求都要重讲一遍"我们产品定位是什么/我们不跟谁比/我们技术栈不支持XX"——mySecond.ai /prd-generator 的核心体验差异就是这一条自动注入。

Load only the workflow needed for the user's current request:

Artifacts are organized **per requirement** inside the selected product project. Read `.agents/references/requirement-record.md` (or this skill's `assets/references/requirement-record.md` before installation) for the shared record, evidence rules and directory resolution. Each requirement has one `需求档案.json` with a stable ID; its folder lives under the project's optional `pm-forge.json` → `artifact_root` (default `.` for compatibility). It holds the used artifact subfolders and `沟通记录.md`. Shared scripts, start-service entries, `.handoff/` and `.agents/` stay at the product project root.

**Folder ownership (applies to ALL four workflows):** Before writing, locate the existing record by `requirement_id` or create/reuse one with `python3 scripts/pm_requirement.py --project <product-project> --name <需求名>` (Windows: `py -3`). Call its parent `REQ_DIR`. All four workflows reuse `REQ_DIR` and update its record; PRD need not come first. Legacy `[需求名]/` paths in the table below refer to `REQ_DIR`, not necessarily a folder directly under the current working directory. Only create subfolders actually used.

For a standalone single-requirement project whose existing `需求文档/` and `原型/` are already at the project root, use `--requirement-dir .` with the record script (from the personal skill if it is not installed there). `REQ_DIR` is then that project root; do not create another `[需求名]/` inside it.

If a project has locally customized workflow files from an earlier version, keep those edits; apply the shared record and evidence rules in `requirement-record.md` when older path examples or simulated-data instructions disagree. Review `.pm-workflow/updates/` before merging later workflow changes.

| User intent                                                   | Read this file first                                    | Primary output                                                                                                                                                                                                         |
| ------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| New requirement, PRD, prototype, flowchart, continue PRD work | `.agents/workflows/edu-pm-prd.md`                       | `[需求名]/需求文档/[需求名]-PRD.html`, `[需求名]/原型/[需求名]-prototype.html`, `[需求名]/流程图/[需求名]-flow.html`, `[需求名]/流程图/[需求名]-screenflow.html` (交互流程图, as needed)                               |
| Demand discovery, user needs, competitive/product insight     | `.agents/workflows/edu-pm-demand.md`                    | `[需求名]/需求挖掘/[需求名]-需求洞察.html`                                                                                                                                                                             |
| Acceptance checklist, test checklist, launch verification     | `.agents/workflows/edu-pm-acceptance.md`                | `[需求名]/验收清单/[需求名]-验收清单.html`                                                                                                                                                                             |
| Metrics, BI-style analysis, report from data                  | `.agents/workflows/edu-pm-data-analysis.md`             | `[需求名]/数据分析/[需求名]-数据分析.html`                                                                                                                                                                             |
| **AI产品发布前 / 模型升级 / 重大功能变更（高风险AI场景）**    | **`.agents/workflows/edu-pm-ai-ethics.md`** (P2-3 新增) | **`[需求名]/需求挖掘/[需求名]-AI伦理审查.html`** + 需求档案.decisions[] 自动追加一条 `choice=boundary_confirmed` 的 D-xxx + artifacts.ai_ethics_review 登记路径（未执行会被 `--audit` 的 AIETHIC-001 阻塞 stage 推进） |

For PRD work, treat `.agents/workflows/edu-pm-prd.md` as the authoritative project workflow. Do not use root-level `edu-pm-prd.md` if both exist.

## PRD Workflow Rules

- **Confirm the requirement before writing when core information is missing; ask only focused questions.** The six-dimension completeness check has a **材料** dimension (§1.2): ask once for the tracking dictionary, design spec / brand accent, and any existing prototype screenshots — finding out at §数据埋点 that no dictionary exists means interrupting the user mid-draft or inventing field names.
- **Carry the confirmation into the document.** §1.4 maps each confirmed item to its PRD location: 核心改动 → 功能清单+详细方案; 成功指标 → 需求目标表; **不做 / 范围外 → 需求概述的「范围块」**; 背景证据 → 需求背景三段式; 跨页规则 → 需求概述规则表. A "不做" that was agreed verbally but never written into the PRD does not count as confirmed.
- **单向真相源：沟通记录不负责存结构化待确认。** 结构化待确认项 **唯一** 写入 `REQ_DIR/需求档案.json` → `open_questions[]`，按 `requirement-record.md` 的 `Q-xxx` 编号维护，有 owner/status/created_at。PRD 正文末尾的「待后续确认的产品口径」清单，**只允许引用 open_questions 的 Q-ID 一句话摘要**（例如 `Q-003 · 埋点字典缺 | Owner=数据团队 | 影响=§七数据埋点参数名`），不允许在沟通记录里再写一份「1. xxx 待确认」编号清单。沟通记录只记录：过程叙述、用户原话、决策结论、以及引用 `D-xxx / Q-xxx / R-xxx / A-xxx / M-xxx` 的 ID。违反会被 `pm_requirement.py --audit` 的 TRUTH-001 报 WARN。
- **统一用 `assets/templates/prd-content.html` 填内容，不要手写 HTML 骨架。**（纯视觉+骨架，详见 Visual-Reference.md V-SKEL-001）
- **交付前跑 `assets/scripts/validate_prd.py` 如实汇报结果。** 机械检查范围包括核心章节、验收表 class/ID/场景与结果列、表头和章节顺序、详细方案原型与描述结构、埋点命名、正文样式位置。**通过 ≠ PRD好，但FAIL=一定没做完。**（纯机械校验，详见Visual-Reference.md V-OUT-004）
- **章节顺序固定，但可按需求规模裁剪（不能静默裁剪，确认时明确哪些留/删）。** 顺序：项目信息→版本记录→需求背景→需求目标→需求概述→业务流程图→交互流程图→详细方案→数据埋点→时序图→上线计划→附录。核心骨架必留：项目信息、版本记录（两张表独立永不合并）、需求背景、需求目标、详细方案。其他7个小需求可删除但必须告知。如果业务流程/交互流程裁剪则不产出对应流程图文件（edu-pm-prd.md §1.3.1）。
- **不设独立的「异常/边界」大章**，边界条件写在所属功能行的【边界说明】块内（详细方案 §2.3.1）。详见 Visual-Reference.md V-SKEL-003。
- **需求目标必须写「用户结果+怎么测」不是实现动作。** 可量化目标进：用户结果/衡量指标/统计口径/预期方向/目标值 5列固定表头表；没有真实基线→写「待基线确认」不编百分比；不可量化也必须可观察可验证；需求背景引用的数据必须给源头或标未确认（§2.2④）。
- **原型单元格两种形式二选一：真实尺寸截图(`<img class="proto-shot">`+外链可点原型) 或 交互式iframe，已有截图不要强行改成iframe。** 详见 Visual-Reference.md V-PROTO-001。
- **详细方案描述块：【页面元素】【交互说明】两个必填，其余按「删了这页面规则还成立吗？」测试。** Y→公共共享规则→放需求概述规则表（§2.3.1③），不重复写3行（签到/累计积分/全局限速/权限矩阵是典型反例）；N→本页规则。【功能逻辑】只写删了本页就不成立的局部规则。禁止写「同上/详见x.x」（单行要独立入评审文档）；禁止写「无」凑字数；每条独立`<p>`/`<li>`进`.desc-block`；多条编号挤在一个段落=缺陷；详细方案描述禁止写技术API/接口措辞。
- **每行=一屏或一个状态变体**（§2.2⑦）。跨三屏二级功能拆3行每行独立原型；一屏多状态单行写【页面元素】；说不清原型这张图片具体是什么→粒度过细回滚。详见 Visual-Reference.md V-SKEL-002。
- **需求概述≠功能清单表**（§2.2⑤）。必须有：范围块（本期范围/本期不做什么·暂不展开）+ 功能清单表 + （必要时）跨页规则小表（`h3`+小表）。整章裁剪时必须只丢功能清单，范围块和公共规则不能丢。
- **需求背景固定三段式**（§2.2⑥）：谁/什么场景/遇到什么问题→影响多大→证据是什么（没证据就说没，不编）。需求目标结尾有「待后续确认的产品口径」清单，汇总全文所有待确认项+Owner+影响。
- **档案关联必须同步**（requirement-record.md 跨阶段追溯）：真实来源/需求/屏/验收/目标用稳定ID连；demo和无证据陈述不算证据；项目信息放`requirement_id`；详细方案行`data-requirement-id`；目标行`data-metric-id`；验收条件表必须用`<table class="acceptance-table">`，每行有`data-requirement-id`，同一R多A时每行加`data-acceptance-id`。具体列契约与旧PRD迁移见 `edu-pm-prd.md` §7.1。
- **编辑模块撤销/重做栈**（§2.7⑤）：⌘Z/Ctrl+Z撤销，⌘⇧Z/Ctrl+Y（或Ctrl+⇧Z）重做，覆盖：文本编辑、行增删、表删、列/行尺寸调整，全部共用一个栈；新编辑清 redo；删行/表以DOM节点（不是HTML字符串）存栈保证控件恢复；`contenteditable`原生撤销必须捕获阶段`preventDefault`，否则两个栈同时触发；纯内存，不承诺刷新后还在（这是展示层行为，保留在SKILL仅因为这是对用户交互的硬承诺，不是产品判断）。
- **时序图放在数据埋点后，是研发/测试向可选章节。** 必须是可复制的Mermaid源码文本块（不是渲染图/iframe），研发测试直接用源码；源码分：端侧编排`sequenceDiagram` + 关键对象`stateDiagram-v2`，每个代码块配「复制源码」按钮+要点说明。这一章允许写技术接口/字段名（§2.3.1禁止技术措辞仅针对详细方案描述块），详见edu-pm-prd.md §4.7。
- **交互流程图放在详细方案前可选章节**：状态摘要卡+原型哈希页链接，导航箭头必须直角/曼哈顿布线；自环边用偏移轨；必须有状态机图例；不允许把整屏原型缩小成小iframe、也不允许贝塞尔/对角箭头。导出服务走本地截图。详见 Visual-Reference.md V-PROTO-004。
- **交付格式：默认HTML，用户明确要Markdown才降级**（Visual-Reference.md V-OUT-001）；HTML原型是核心交互物，Pencil只做视觉增强可选，不喧宾夺主；修改PRD/原型/流程图任意一个，另两个必须查一致性；图像导出统一走`prototype-export-client.js`+本地服务，禁止重写`html2canvas/html-to-image`（Visual-Reference.md V-PROTO-005）。
- **「一键复制全文」原型iframe转base64**：必须走本地`POST /api/snapshot`服务，缓存优先+文件修改时间失效重渲染；禁止`iframe.remove()`丢原型。`file://`协议下浏览器禁本地fetch和canvas读回，所以base64只能靠服务；分3级降级并**如实告知用户丢了什么**（edu-pm-prd.md §2.8），详见Visual-Reference.md V-OUT-002。
- **粘贴糊了先加MAX_IMG_WIDTH不要动压缩器**：实测1200px下 JPEG .85/.95/WebP .92/PNG无损 分辨率没区别，糊在缩放不在压缩。默认2000px @ q0.9（Visual-Reference.md V-OUT-003）；粘贴图要放大到1000px以上验清晰度，原型列≈335px宽度下全分辨率看起来都一样，证明不了任何事；剪贴板大小按base64 payload字节（1.33×真实字节）报告，不用解码字节数。
- **`原型截图/`目录是PM资产不是临时目录**：导出清理时只清`.export-manifest.json`登记过的文件名——**绝不`glob *.png`删**。已经有一次导出`-prototype.html`单图时用glob把8张手工截图（不在git）全删光的事故记录（edu-pm-prd.md §4.4第6条）。
- **双栏预览默认关闭**：打开PRD是纯文本阅读态；点「双栏预览」才出面板（按钮文案切换为「收起预览」），iframe src首次开前保持空不空转；原型目录非空也不自动开；唯一自动开是`#preview=<page-id>`哈希。面板必须带`－/％/＋/适配`缩放4件套，`previewZoom`只存JS变量不写进DOM，复制/保存时不带脏状态（Visual-Reference.md V-PROTO-002/V-PROTO-003）。
- **业务流程图禁用Mermaid默认主题**：`theme:'base'`+固定themeVariables（背景#faf9ff、边#cbc4e7、深字#30285b、连线#8d82b1）、`curve:'linear'`直角、nodeSpacing≥60 rankSpacing≥70；共享页面外壳（#f8f8fc底、14px圆角卡片）；节点形状区分节点类型，**不用填充色区分**，详见Visual-Reference.md。
- **流程图/交互流程图 0文字重叠是硬门槛**（§4.3② §4.6③④）。修复顺序：加画布→扩间距→重布线/加滑轨→拆2张画布；**严禁用改小字号/删标注/删分支/盖背景色来遮重叠**。交付前必须通过几何审计`ok:true` + 100%独立看+嵌入iframe双视角，60%干净的嵌入后一定还叠（edu-pm-prd.md §4.6④有审计代码+导出时硬拦截）。
- **HTTP环境下PRD功能必须全部降级可用**：内网`navigator.clipboard`/`ClipboardItem`/`showSaveFilePicker`不可用时，复制走`execCommand`兜底、保存退化成下载副本；导出服务必须按项目相对路径算调用页来源，否则`/api/snapshot` `/api/asset`返回400后一键复制会静默丢所有图。详见 Visual-Reference.md V-PROTO-006。
- **交付前三件套必须跑通**：① 实际点原型页能渲染不报错；② PRD描述和原型页匹配；③ `validate_prd.py`跑通无FAIL（Visual-Reference.md V-OUT-004）。

## Optional Pencil Path

Offer Pencil enhancement only after the HTML prototype is usable, or when the user asks for high-fidelity design. If Pencil is used:

- Confirm Pencil is running and the MCP connection is available.
- Keep HTML and Pencil color/spacing decisions synchronized.
- Use Pencil screenshots as visual validation, but keep the HTML prototype as the PRD iframe source.

## Output Structure

Per-requirement folders under the product project's configured `artifact_root` (`.` by default); shared tooling stays at the project root. The layout below shows the default.

```text
[需求名]/                  one top-level folder per requirement
  需求档案.json              stable ID, evidence, links, metrics and decisions
  需求文档/                  PRD HTML
  原型/                     interactive prototype HTML and optional .pen
  原型截图/                  exported PNG screenshots (this requirement)
  流程图/                    flowchart HTML + screenflow (交互流程图) HTML
  数据分析/                  data analysis reports (created on demand)
  验收清单/                  acceptance checklists (created on demand)
  需求挖掘/                  demand analysis reports (created on demand)
  沟通记录.md                per-requirement conversation log

scripts/                  [shared] prototype export service
启动原型导出服务.command     [shared] macOS — optional manual start; normally the service
                                   auto-starts on the first export click (launchd socket activation)
启动原型导出服务.bat         [shared] Windows — double-click and keep the window open
.handoff/                 [shared] cross-session handoff files
.agents/workflows/        [shared] editable workflow definitions
.agents/references/requirement-record.md  [shared] record contract
pm-forge.json              [optional] artifact_root inside this product project
.agents/skills/edu-pm-workflow/assets/
  templates/prd-content.html   PRD body skeleton — copy and fill, do not hand-write
  scripts/validate_prd.py      mechanical PRD validation — must pass before delivery
  scripts/pm_requirement.py    create/reuse the requirement record
```

## Customization

Edit `.agents/workflows/*.md` for project-specific behavior. Edit the bundled files under `.agents/skills/edu-pm-workflow/assets/workflows/` only when changing the reusable skill template for future installs.
