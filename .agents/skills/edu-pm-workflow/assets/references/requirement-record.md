# 需求档案：跨工作流的最小契约

每个需求目录只有一份 `需求档案.json`。它记录稳定身份和产物之间的关系；PRD、原型、验收清单与数据报告仍各自保持适合阅读的格式。某个工作流可独立开始，缺少上游材料时留空并记录待确认项。

## 项目与目录

- 先确定**产品项目根目录**，在该项目内运行工作流。维护本 skill 的 PM-Forge 仓库不是产品项目；用户在仓库里描述另一个产品时，先定位那个产品的目录，再落盘。
- 可选 `pm-forge.json` 放在产品项目根目录，键 `artifact_root` 是项目内相对目录，如 `"requirements"`。未配置时用 `"."`，兼容已有的 `[需求名]/`。不要把产物写到项目外，也不要因目录名相似而迁移旧产物。
- 首次落盘或找不到档案时运行 `python3 scripts/pm_requirement.py --project <项目根> --name <需求名>`（Windows：`py -3`）。已有目录会补建档案；已有档案会复用 `requirement_id`，不得重新编号或覆盖。
- 后续工作流优先按 `requirement_id` 或现有档案定位需求；同名、改名或目录有歧义时先核对档案。下文把档案所在目录称为 `REQ_DIR`。旧流程里的 `[需求名]/` 与 `{需求名称}/` 路径示例均映射到 `REQ_DIR`。
- 原型、流程图和 PRD 的跨文件相对链接，以**实际文件位置**计算；当 `artifact_root` 不为 `"."` 时，不照抄示例中的 `../../scripts/`。共享脚本始终在产品项目根的 `scripts/`。

## 档案字段

`schema_version`、`requirement_id`、`title`、`stage`、`created_at`、`updated_at`、`sources`、`requirements`、`metrics`、`acceptance`、`decisions`、`open_questions`、`artifacts` 是基础字段。保留未知字段，便于项目扩展；不要为了运行某一工作流清空别的工作流填写的内容。

| 字段 | 记录规则 |
|---|---|
| `sources[]` | `id`（`SRC-001` 起）、`classification`（`evidence` / `claim` / `assumption` / `demo`）、`kind`、`source_ref`、`collected_at`、`summary`。真实证据需可追溯来源；无来源的口述按 `claim` 记录；AI 生成示例按 `demo` 记录，不能作为用户研究样本或定量结论。 |
| `requirements[]` | `id`（`R-001` 起）、`summary`、`source_ids[]`、`screen_ids[]`、`acceptance_ids[]`、`metric_ids[]`。`screen_ids` 使用原型 hash 页 / PRD `data-preview` 的页面 ID。从真实证据到功能项的关联应能在这里查到；尚无证据时标明假设。 |
| `metrics[]` | `id`（`M-001` 起）、`name`、`definition`、`baseline`、`target`、`window`、`source_ref`、`result`。没有基线或结果用 `null`，不编数字。 |
| `acceptance[]` | `id`（`A-001` 起）、`requirement_id`、`status`（`pending` / `passed` / `failed` / `skipped`）、`evidence_ref`、`checked_at`。浏览器临时进度不是最终验收记录。 |
| `decisions[]` | `id`（`D-001` 起）、`date`、`choice`（`continue` / `iterate` / `stop`）、`basis_ids[]`、`next_action`。没有上线数据时只能记录“待判断”，不可写成已验证的决策。 |
| `artifacts` | `discovery`、`prd`、`prototype`、`flow`、`screenflow`、`acceptance`、`analysis` 等键，对应相对 `REQ_DIR` 的文件路径；只记录实际存在的产物。 |

`stage` 使用 `discovery`、`defined`、`ready`、`shipped`、`measured`、`closed`。它表示已获得的证据与交付状态，不强制按顺序执行工作流。缺少真实上线数据时不得标记 `measured`；只有作出有依据的继续、迭代或停止决定后才标记 `closed`。

正式验收文件 `验收清单/验收结果.json` 至少包含 `schema_version: 1`、与档案一致的 `requirement_id`、`items[]`。每个 item 包含 `id`（`A-*`）、`requirement_id`（`R-*`）、`status`、`checked_at`、`evidence_ref`；未执行项用 `pending` 与 `null`，不能凭页面中的本地草稿判定通过。

## 更新约定

1. 工作流开始时读取档案，只追加或修正当前任务涉及的字段；保留已有 ID 和关系。每次实际修改档案后更新 `updated_at` 为带时区的 ISO 8601 时间。
2. 输出文件写入后更新 `artifacts`。引用的 `source_ids`、`acceptance_ids`、`metric_ids` 必须在相应列表存在；未完成的关联写入 `open_questions`，并记录负责人或待补材料。
3. PRD / 原型 / 流程图变更时检查对应需求项及验收项是否仍一致。验收完成后将结果和证据写入 `acceptance`；数据分析完成后把实际结果写入 `metrics`，再记录下一步决定。
4. 公开的 skill 仓库存放方法、模板与脚本。真实用户反馈、业务数据、截图、令牌及项目产物留在产品项目中，由该项目自行决定版本控制与共享范围。
