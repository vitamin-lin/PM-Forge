# PM Workflow 视觉 / 展示规范参考（P3-3 抽离）

**本文件只放纯展示/输出/视觉层的硬性规则，不涉及产品判断、业务完整度、阶段推进等技能层逻辑。**
产品级判断、业务任务卡、证据追溯、阶段推进规则统一在 `SKILL.md` 主入口 / `requirement-record.md` / `edu-pm-*.md` 工作流里维护。

---

## A · PRD HTML 骨架 & 样式

| 规则ID | 规则 | 背景（为什么硬约束） |
|---|---|---|
| V-SKEL-001 | **一律复制 `prd-content.html` 填内容，绝不手写 HTML 骨架** | class 名、固定表头、`colgroup` 宽度、`desc-block` 结构、`data-preview` 锚点全部预置好。历史缺陷（`<br>` 代替 `<p>` / 列数错 / 缺 `colgroup` 等）90% 来自手写骨架。 |
| V-SKEL-002 | 需求表每行 = 一屏 / 一个状态变体 | 跨三屏的二级功能拆成 3 行，每行独立原型；一屏多状态留在同一行内用【页面元素】逐条写。如果「原型这张图你点不开」→ 粒度过细，回滚。 |
| V-SKEL-003 | **不设独立的「异常 / 边界」大章**，边界条件写在所属功能行的【边界说明】块里（§2.3.1） | 避免出现「异常/边界 10 条但找不到对应功能行」的脱节问题。 |
| V-SKEL-004 | 详细方案行统一写 `data-requirement-id="R-xxx"`；同一 R 有多条验收行时补充 `data-acceptance-id="A-xxx"` | `pm_requirement.py --sync-acceptance-from-prd` 靠这两个属性精确匹配。没写 A-ID 会按 scenario 匹配，1R 多 A 容易匹配失败。 |
| V-SKEL-005 | 目标行统一写 `data-metric-id="M-xxx"` | 指标追溯靠这个属性。 |

---

## B · 原型展示（双栏 / 缩放 / 截图 / iframe）

| 规则ID | 规则 | 背景 |
|---|---|---|
| V-PROTO-001 | 【原型】单元格接受两种形式，二选一即可：① 高清截图 `<img class="proto-shot">` 带真实宽高 + 外链接可点原型；② 交互式 iframe | 不要为了统一把已经有的截图强行包成 iframe，徒增复杂度。 |
| V-PROTO-002 | **双栏预览默认关闭**，只有用户点「双栏预览」按钮才出现；`iframe src` 首次打开前保持空；显式 `#preview=<page-id>` 哈希可自动开。 | 打开 PRD 是阅读态，不是调试态，不能一上来就跑 iframe 消耗性能。 |
| V-PROTO-003 | 双栏缩放控件固定为 `－ / % / ＋ / 适配` 四件套；`previewZoom` 只放 JS 变量，绝不写进 DOM。 | 复制/保存出来的 HTML 不能带运行时状态，否则导出/分享就脏了。 |
| V-PROTO-004 | 交互流程图（screen flow）导航箭头必须**直角曼哈顿布线**，禁止贝塞尔/对角；同屏自环边用偏移轨；必须配状态图例。 | 对角箭头容易把交叉关系看错，研发/测试读不懂。 |
| V-PROTO-005 | 原型、流程图、交互流程图**统一走 `scripts/prototype-export-client.js` → 本地服务导出 PNG**，禁止重新实现 `html2canvas` / `html-to-image`。 | 三者走一条路径才能保证导出效果一致、缓存命中、失败信息统一。 |
| V-PROTO-006 | 所有 HTTP 环境功能必须有降级：`navigator.clipboard` 失败用 `execCommand('copy')`；`showSaveFilePicker` 失败用下载副本；`/api/snapshot` 按项目相对路径回退解析。 | 内网 HTTP 部署环境占用户实际的 40%+，Clipboard/File System Access API 全部不可用。 |

---

## C · 交付 & 导出

| 规则ID | 规则 | 背景 |
|---|---|---|
| V-OUT-001 | 优先交付 HTML 格式产物，用户明确要 Markdown 再降级。 | 双栏 / 原型 / 截图导出 / 可勾选验收 只有 HTML 能承载。 |
| V-OUT-002 | 一键复制全文 = 文字 + 原型/流程图导出 PNG 转 base64 内联，丢图必须在 UI 上明确说缺了几张。 | 复制到飞书/钉钉/邮件是评审的最常用动作，静默丢图 = 评审会变成灾难。 |
| V-OUT-003 | 图片默认 2000px / 质量 0.9，可在 `pm-forge.json` 改 `export.image_width` / `export.quality`。 | 2000px 是「放大看细节清晰 + 文件不太大」的平衡点。 |
| V-OUT-004 | 交付前必须跑：① 实际点一下原型页渲染不报错；② PRD 描述和原型页匹配；③ `python3 scripts/validate_prd.py` 通过（见 SKILL.md §3）。 | 视觉类 90% 的漏判都能被这三步抓住。 |

---

## D · 产品规范 vs 展示规范分层表（给维护者）

```
PM-Forge 分层（维护时请先判断属于哪一层再下笔）
│
├─ SKILL.md 主入口 → 产品判断层：
│   · 路由表（什么时候走什么工作流）
│   · Step 0 Context Ingestion（自动读产品宪法）
│   · AI 伦理 / 单向真相源 等跨工作流的硬原则
│
├─ edu-pm-*.md 工作流 → 过程层：每个工作流怎么一步步做、输出什么格式
│
├─ requirement-record.md → 数据契约层：需求档案 JSON 的字段和跨文件关联
│
├─ Visual-Reference.md → VISUAL LAYER（本文件）：纯展示 / 输出 / 视觉硬约束
│   （以上4条路径互斥，不要跨层写内容）
│
└─ scripts/*.py → 机械校验层：只查「类名/数量/顺序/id 存在性」，绝不做语义判断
```
