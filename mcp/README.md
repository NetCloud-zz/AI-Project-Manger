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

## 安装

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
