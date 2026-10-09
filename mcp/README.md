# MCP / Agent Skills

本目录提供面向 **Claude Code**、**Cursor Agent**、**OpenAI Codex** 的项目 Skills。

Skills 是给 AI 编程助手读的说明文件（`SKILL.md`），不是运行时 MCP Server。
若你要挂载真正的 MCP Server，可在各工具的配置里自行添加；本仓库优先提供可复用的技能包。

## 目录

| Skill | 用途 |
| --- | --- |
| `project-agent-overview` | 架构、边界、目录、开源约定 |
| `project-agent-assistant` | 项目助手 / 流式对话 / 工具与锁 |
| `project-agent-deploy` | 本地与 Docker 部署、配置与排障 |
| [project-agent-database](skills/project-agent-database/SKILL.md) | 数据库字段、关系、权限、迁移和助手工具维护 |

## 数据库详情入口

从 [database/README.md](database/README.md) 按任务查阅字段字典、关系、ER 图、JSON 结构、YAML 语义层、查询规则、工具契约和已知风险。完整详情统一保存在 `docs/database`，此目录通过相对链接关联，不另存一份结构快照。

[database/resources.json](database/resources.json) 提供机器可读的文件索引；其中路径相对于仓库根目录。它是文件导航，不是运行中的 MCP 服务注册配置。

后续数据库相关开发先读取 [数据库维护技能](skills/project-agent-database/SKILL.md)。资料标注的结构采集日期与当前代码、已部署数据库应分别核对，不能把旧采集结果当实时状态。

项目助手实际加载的是后端 [工具定义](../backend/app/agents/database_tools.py) 和 [执行器](../backend/app/agents/management_tools.py)。Skills 文档更新本身不改变运行时工具或数据库结构。

## 安装

复制技能后仍需保留完整项目中的 `mcp/database` 和 `docs/database`。若安装目录改变导致相对链接失效，按技能中注明的仓库根目录路径定位资料；只复制 SKILL.md 不会自动带上数据库详情。

### Cursor

```bash
mkdir -p .cursor/skills
cp -R mcp/skills/* .cursor/skills/
```

或在 Cursor 设置中把本仓库 `mcp/skills` 加入项目 skills 路径。

### Claude Code

```bash
mkdir -p .claude/skills
cp -R mcp/skills/* .claude/skills/
```

### Codex

将 `mcp/skills/*/SKILL.md` 内容纳入项目 `AGENTS.md`，或复制到 Codex 支持的 skills 目录（以当前 Codex 文档为准）。本仓库根 `README` 与 `docs/HANDBOOK.md` 亦可作为全局上下文。

## 版权

Skills 文本与本项目相同，Copyright Jack Zhang，Apache License 2.0；署名不得删除。
