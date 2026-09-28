---
description: PM AI 产品伦理审查工作流：适用于 AI/大模型/智能体类产品发布前、模型升级、重大功能变更（高风险 AI 场景），输出 6 维负责任 AI 审查报告 + 风险分层打分表 + 强制 Mitigation 行动
---
# AI 伦理审查工作流（负责任 AI 发布前把关）

> 本工作流灵感参考 `pm-claude-skills/ai-ethics-review` SKILL 的 6 维审查框架，强制要求：每条风险都必须关联需求档案的 R/M/SRC ID，审查结束后自动追加一条 D-xxx `choice=boundary_confirmed` 决策记录到需求档案。
> 本工作流会被 `pm_requirement.py --audit` 的 `AIETHIC-001` 阻塞：**AI 类需求 stage ≥ ready 时 artifacts.ai_ethics_review 没登记路径 → 报错拒绝推进**。

## 适用场景
- AI 产品发布前（v1.0 正式上线 / 从 Beta 切 GA）
- 主模型升级（例如从 gpt-4o-mini 切到 gpt-4o）
- 重大功能变更：新增核心 AI 能力、PII 处理范围扩大、接入新的三方 API
- EU AI Act 被标为 High Risk 或以上的项目（每次 stage 推进都必须跑一次）

## 触发时机（和 edu-pm-prd 工作流的配合）
- 位置：edu-pm-prd 步骤七 7.2 推 stage 到 defined 之后、推 ready **之前**
- 如果没跑本工作流、artifacts.ai_ethics_review 为空 → `--push-stage ready` 会被 AIETHIC-001 报错拒绝

## 需求目录与档案（落盘前必读）
和 edu-pm-prd 共用同一个 `REQ_DIR`。先读取 `.agents/references/requirement-record.md`，定位到目标需求的 `需求档案.json`。输出 HTML 报告放在 `REQ_DIR/需求挖掘/`，文件命名：`{需求名称}-AI伦理审查.html`。

**审查结束强制回写 3 件事**（不做就不算完成，7 件套的同逻辑）：
1. `需求档案.artifacts.ai_ethics_review` 登记报告相对 REQ_DIR 的路径
2. 追加一条 decisions[]：`D-xxx choice=boundary_confirmed`，关联所有 SRC/R/M ID 和 风险 ID
3. 沟通记录追加 4 行摘要（格式见§6）

---

## 步骤 1：收集审查所需材料（6+1 类）
以下材料任何一类缺失，在审查报告里用 **红色 ⚠️ 缺失** 标记，不允许报"全部通过"：

| 材料分类 | 从哪里来（自动关联需求档案已有内容） | 没有时怎么取数 |
|---|---|---|
| **用户画像** | `product.md / personas.md`（产品宪法里的 Persona-A/B）或档案的 `R.owner` | 追问用户：本次上线影响的 3 类主要用户 |
| **能力清单 & 模型版本** | PRD `ai-boundary-card`（AI-1 模型选型）里的能力场景 × 主模型/降级策略 | 没有就先补 PRD AI-1 块 |
| **PII 与合规红线** | `product.md §3.2 合规红线` + `ai-safety-card`（AI-3） | 追问：合规团队、法务审核过吗？ |
| **幻觉兜底 & HITL** | PRD `ai-hallucination-card`（AI-2）里的置信度阈值 + 拒绝话术 + HITL 路由 | 没有就先补 PRD AI-2 块 |
| **评测方案 & 通过率** | PRD `ai-eval-card`（AI-4）里的黄金测试集条目数 × 通过率 × 抽样复审率 | 没有就先补 PRD AI-4 块 |
| **现有指标与目标** | 需求档案 `metrics[]` + `AIMETRIC-001` 要求的 hallucination/escalation/avg_confidence 品质指标 | 指标为空时直接阻塞：先加品质指标 |
| **附加材料**（可选）：服务条款、数据处理协议 DPA、合规团队的意见书 | 从项目 `.pm-product-context/product.md` 或用户手动提供 | 没有就标为「用户说明：暂无合规意见书」 |

---

## 步骤 2：6 维度审查（每维度 3 级打分 = 红绿黄；每条风险写 Mitigation）

### 2.1 Fairness · 公平性
- 审查点：会不会对某个人群产生**系统性歧视或差异结果**？（例如：教育课消对老年老师不友好、报销对少数民族不友好）
- 支撑证据来源：`R-xxx / SRC-xxx / M-xxx` ID
- 每条风险写 3 要素：风险描述 → 触发阈值 → Mitigation（Owner + 完成前 stage）

### 2.2 Transparency · 透明性
- 审查点：**用户能否知道这是 AI 生成的内容？**
- 强制必过清单（任一条不满足就打红，属于 EU AI Act 对 General 的基本要求）：
  1. UI 上有明确的「内容由 AI 辅助生成，请人工复核」水印或文案
  2. 点击**可以展开**查看：模型名称 + 版本 + 是否经过人工复核
  3. 用户可以**一键切换**：关闭 AI 辅助、手动重写

### 2.3 Privacy & PII · 隐私与个人信息保护
- 审查点：**哪些 PII 进了模型？出境了吗？脱敏了吗？**
- 强制要求：
  - 列出全部 PII 字段（手机号、身份证、姓名、组织、交易记录、地址、邮箱…）
  - 每个字段写明：**允许入模型 Y/N**；若 Y：脱敏方式？模型服务方是否做数据隔离？保留天数？
  - EU AI Act 为 High Risk 或以上：必须有 DPA、用户知情权通知、GDPR 下的「遗忘权」实现方式

### 2.4 Safety & Harm · 安全与伤害预防
- 审查点：**幻觉或攻击性输出会不会造成真实伤害？**
- 典型 4 类（每类至少 1 条 Mitigation）：
  1. 幻觉→错误推荐导致用户损失（报销记错、课消错扣）：Mitigation
  2. Prompt 注入→泄露用户 PII/系统提示词：Mitigation（AI-3 已写的黑名单/长度上限）
  3. 连续低置信度→用户反复尝试，产生情绪/时间伤害：Mitigation（自动升 HITL 的阈值）
  4. 模型输出歧视、仇恨、违法内容→传播：Mitigation

### 2.5 Accountability & Audit · 可追责与可审计
- 审查点：**出了问题，能不能追溯到某次具体调用？谁负责？**
- 强制必过：
  1. 每次调用日志保留≥90天：`request_id × user_id × 模型版本 × 输入输出哈希 × 时间戳`
  2. `D-xxx` 决策：如果某次审查打了**黄**（接受风险），必须由 `decided_by` 明确到人/团队
  3. 重大安全事件的回滚机制：模型降级开关、一键切旧版本、HITL 全开的红名单

### 2.6 Societal Impact · 社会与环境影响（可选但推荐）
- 审查点：长期使用后会不会产生系统性社会影响？（例如：AI 自动审批会不会让某地区申请通过率下降？）
- 没材料就标：「暂无法评估，上线 3 个月后补审」

---

## 步骤 3：5 因素风险分层打分（Consequentiality / Scale / Reversibility / Vulnerability / Transparency）

5 因素 × 每因素 1-5 分 → 合计得分 5-25，最终映射成 L/M/H：

| 因素 | 1 分（低） | 5 分（高） | 本项目实得分（1-5） |
|---|---|---|---|
| Consequentiality 结果严重性 | 只是推荐建议，最终人工拍板 | 自动执行真实经济结算（钱/权限/资源变更） | |
| Scale 影响规模 | < 500 DAU | > 10万 DAU / 全量用户 | |
| Reversibility 可逆性 | 一键回滚，1小时恢复 | 不可逆（真实写入外部系统） | |
| Vulnerability 用户脆弱性 | 面向专业从业者 | 面向老人/未成年人/弱势群体 | |
| Transparency 决策透明性 | 用户100%知道AI在做什么 | 决策过程黑盒，用户完全看不到 | |

**总得分 → 分层：**
- **L（Low，总分 5-10）**：正常审核流程，Mitigation 全过即可
- **M（Medium，11-17）**：必须有法务/合规团队书面签字（或文档明确通过）
- **H（High，18-25）**：必须有 2 次独立复审，CEO/CTO 级签字

---

## 步骤 4：Mitigation 表格化（每条风险写「完成 before which stage」）

强制模板（每个步骤 2.1-2.4 识别的风险，都写一行）：

| Risk ID | 所属维度 | 风险描述（关联 SRC/R/M ID） | 触发阈值 | Mitigation 动作 | Owner | 必须在 stage ___ 前完成 |
|---|---|---|---|---|---|---|
| RISK-001 | Fairness | （例）报销对老年老师的繁体字识别准确率低（SRC-007 / M-004） | < 85% | 增加 1000 份繁体字报销单做专门微调集，准确率≥90%才上线 | 数据组 · 张XX | ready |

---

## 步骤 5：合规声明占位（强制写，不许留空）

- **EU AI Act Classification**：Unacceptable / High / General / Minimal（二选一写清楚依据）
- **NIST AI RMF 1.0 映射**：Govern / Map / Measure / Manage 四个功能，本项目各覆盖了哪些
- **结论**：✅ 同意发布 / ⚠️ 有条件同意（见 Mitigation 完成情况）/ ❌ 不同意

---

## 步骤 6：回写需求档案 3 件套 + 沟通记录摘要（7 件套同逻辑，缺 1 不算完成）

### 6.1 登记报告路径
```bash
python3 scripts/pm_requirement.py \
  --project <产品项目根> --name "<需求名>" --requirement-dir . \
  --update \
  --add-decision "AI伦理审查通过：6维度×5因素得分=XX，RISK-001~RISK-N Mitigation 已在 stage ready 前完成" \
  --choice boundary_confirmed \
  --basis-ids "SRC-001,R-002,M-003" \
  --decided-by "AI审查委员会（产品+合规+数据）"
```

### 6.2 追加 decisions[] D-xxx
执行上面的 `--update --add-decision` 会自动编号。

### 6.3 沟通记录追加 4 行摘要（固定格式）
```
【AI伦理审查摘要 · D-xxx】
  · 审查对象：本次发布的 XX/YY/ZZ 3 个 AI 能力，模型版本：XXX
  · 5因素总分：XX/25 → 风险分层：L/M/H
  · RISK 条数：共 N 条；其中 before-ready：M 条；before-shipped：K 条
  · 结果：✅/⚠️/❌ + Mitigation Owner + 下次复审时间
```

---

## 附录：HTML 报告骨架（必须用 prd-content.html 的 style 约定复用视觉）

必须保留的标题顺序：项目信息 → 版本记录 → 6 维度审查结果（每维度独立卡片）→ 5 因素打分表 → Mitigation 风险表 → 合规声明 → 关联 SRC/R/M/D ID 交叉引用表
