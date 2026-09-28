# PM-Forge

PM-Forge 是一套面向产品经理的 AI 工作流。它把需求整理、产品方案和交付物生成串在一起，适用于不同业务领域与产品形态。

工作流可协助产出 PRD、交互原型、业务流程图、需求洞察、验收清单和数据分析报告；配套的本地服务负责预览、截图导出，以及 PRD 中的原型图片处理。

## 能做什么

- **需求文档**：按需求规模组织 PRD 章节，包含背景、目标、范围、详细方案和待确认项。
- **交互原型与流程图**：生成可浏览的 HTML 原型、业务流程图和跨页面交互流程图。
- **需求分析**：整理用户场景、问题、机会和策略建议。
- **验收清单**：生成可在浏览器中勾选的功能验收清单。
- **数据分析**：根据提供的数据制作指标、图表和结论报告。
- **闭环档案**：用稳定需求 ID 连接证据、方案、验收、上线指标和下一步决定；缺数据时保留待验证状态。
- **本地导出服务**：用真实浏览器渲染页面并导出 PNG，也支持 PRD 的原型图片处理。

产物按需求名归档。不同工作流会复用同一个需求目录，只创建实际需要的子目录：

```text
[需求名]/                    # 默认位置；可通过 pm-forge.json 设置 artifact_root
├── 需求档案.json             # 来源、需求项、指标、验收与决策的关联
├── 需求文档/
├── 原型/
├── 流程图/
├── 原型截图/
├── 需求挖掘/
├── 验收清单/
├── 数据分析/
└── 沟通记录.md
```

## 快速开始

### 获取项目

```bash
git clone https://github.com/vitamin-lin/PM-Forge.git
```

在 Codex 中打开 PM-Forge 仓库即可查看和二次开发这套工作流。

如果希望在多个项目里使用同一份个人 skill，在本仓库先运行 `python3 scripts/sync_personal_skill.py --check` 查看与个人副本的差异，再运行 `python3 scripts/sync_personal_skill.py --sync` 同步到 `~/.codex/skills/edu-pm-workflow/`。已有个人副本且内容不同的情况下，脚本会先停止并要求显式使用 `--yes`；确认差异后再覆盖。此后在目标产品项目运行该个人 skill 的 `scripts/initialize.py --project <目标项目>`。

### 安装到其他项目

需要 Python 3.9 或更高版本。下面是把 skill 一同放进目标项目的另一种方式：先复制技能目录，再运行初始化器。仅运行初始化器会安装流程文件和服务，但不会复制技能本体。

macOS / Linux：

```bash
mkdir -p "/path/to/your-project/.agents/skills"
cp -R "/path/to/PM-Forge/.agents/skills/edu-pm-workflow" \
  "/path/to/your-project/.agents/skills/"
python3 "/path/to/your-project/.agents/skills/edu-pm-workflow/scripts/initialize.py" \
  --project "/path/to/your-project"
```

Windows（PowerShell）：

```powershell
$skillDir = "C:\path\to\your-project\.agents\skills"
New-Item -ItemType Directory -Force -Path $skillDir
Copy-Item -Recurse "C:\path\to\PM-Forge\.agents\skills\edu-pm-workflow" $skillDir
py -3 "C:\path\to\your-project\.agents\skills\edu-pm-workflow\scripts\initialize.py" --project "C:\path\to\your-project"
```

安装后，在 Codex 中打开目标项目并直接描述需求。工作流会根据任务选择需求挖掘、PRD、验收清单或数据分析流程。也可以在项目目录中双击对应的 `init.sh` 或 `init.bat` 安装。

首次创建某条需求时，工作流会在**目标产品项目**里建立 `需求档案.json`，并在后续步骤复用稳定 ID。需要自定义产物位置时，将目标项目的 `pm-forge.json.example` 复制为 `pm-forge.json`，把 `artifact_root` 设为项目内相对目录，例如 `"requirements"`；默认 `"."` 与旧项目兼容。产品产物留在目标项目，PM-Forge 仓库作为公开的 skill 源码维护。

安装器可重复运行。运行时服务代码会更新；用户编辑过的工作流和模板会保留，新版本副本会写入目标项目的 `.pm-workflow/updates/` 供合并。使用 `--no-launcher` 可跳过 macOS 按需启动器注册：

```bash
python3 "/path/to/your-project/.agents/skills/edu-pm-workflow/scripts/initialize.py" \
  --project "/path/to/your-project" --no-launcher
```

## 导出与排查

macOS 安装时默认注册按需启动器。用户点击导出时服务会自动启动；也可以双击 `启动原型导出服务.command` 手动启动。

Windows 上双击 `启动原型导出服务.bat`，保持窗口打开，再从原型或流程图页面导出。

需要检查运行环境时，在已安装工作流的项目目录执行：

```bash
python3 scripts/start_service.py --doctor
```

Windows 使用：

```bat
py -3 scripts\start_service.py --doctor
```

服务需要 Python 3.9 或更高版本。首次运行时会准备共享运行环境，并优先使用系统中已有的 Edge 或 Chrome；找不到可用浏览器时，可能需要下载 Playwright Chromium。

## 仓库结构

| 路径 | 用途 |
|---|---|
| `.agents/skills/edu-pm-workflow/SKILL.md` | AI 技能入口和通用工作规则 |
| `.agents/skills/edu-pm-workflow/assets/workflows/` | 可复用的 PRD、需求挖掘、验收和数据分析流程模板 |
| `.agents/skills/edu-pm-workflow/assets/templates/` | PRD 正文骨架、绘图提示词等模板 |
| `.agents/skills/edu-pm-workflow/assets/scripts/` | 安装器要分发的服务代码、校验器和模板脚本 |
| `.agents/skills/edu-pm-workflow/assets/references/requirement-record.md` | 需求档案、证据来源与跨产物关联约定 |
| `.agents/skills/edu-pm-workflow/scripts/` | 跨平台安装入口 |
| `.agents/workflows/` | 此仓库当前项目使用的工作流文件 |
| `scripts/` | 安装在此仓库中的导出服务和 PRD 校验工具 |
| `启动原型导出服务.command` / `.bat` | macOS / Windows 手动启动入口 |
| `关键点.md` | 工作流演进记录和经验 |
| `.mcp.json.example` | 可选的 Pencil MCP 配置示例 |

`.pm-workflow/` 保存安装状态和本机运行配置；`.handoff/` 保存本地交接文件。这些运行数据已从 Git 提交中排除。

## 二次开发

修改可复用规则时，优先改技能包中的源文件：

| 修改内容 | 源文件 |
|---|---|
| 技能说明和任务路由 | `.agents/skills/edu-pm-workflow/SKILL.md` |
| PRD / 需求挖掘 / 验收 / 数据分析规则 | `.agents/skills/edu-pm-workflow/assets/workflows/` |
| PRD 正文结构 | `.agents/skills/edu-pm-workflow/assets/templates/prd-content.html` |
| 导出服务和运行环境 | `.agents/skills/edu-pm-workflow/assets/scripts/` |
| 安装行为 | `.agents/skills/edu-pm-workflow/scripts/initialize.py` |

工作流规则安装到项目的 `.agents/workflows/`，运行时文件安装到 `scripts/`。修改源文件后，可在仓库根目录重新安装到当前仓库：

```bash
python3 .agents/skills/edu-pm-workflow/scripts/initialize.py --project .
```

安装器会覆盖服务运行时代码，并为被改过的工作流或模板保留新版本副本；发生冲突时，到 `.pm-workflow/updates/` 对照合并。确认源文件和安装副本一致后，再提交改动。

本地运行配置 `scripts/pm-runtime-config.js`、虚拟环境、Python 缓存和 macOS 元数据不会提交。`.mcp.json.example` 中的 Pencil 命令是 macOS ARM 路径示例，使用前需按本机 Pencil 安装位置调整。

## 相关文档

- [技能说明](.agents/skills/edu-pm-workflow/SKILL.md)
- [技能包说明](.agents/skills/edu-pm-workflow/README.md)
- [PRD 工作流](.agents/workflows/edu-pm-prd.md)
- [需求挖掘工作流](.agents/workflows/edu-pm-demand.md)
- [验收清单工作流](.agents/workflows/edu-pm-acceptance.md)
- [数据分析工作流](.agents/workflows/edu-pm-data-analysis.md)
