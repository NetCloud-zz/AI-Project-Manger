# LLM 提示词目录

本目录集中管理所有发送给大模型的提示词。**每个提示词一个 `.md` 文件**，Python 代码不再内联提示词文本。

## 使用方式

```python
from app.prompts import load_prompt, render_prompt

SYSTEM_PROMPT = load_prompt("management_agent")           # 原样读取
instruction = render_prompt("structured_output_instruction", schema=...)  # 带占位符
```

`load_prompt` 带缓存，进程内只读一次磁盘。

## 文件清单

| 文件 | 使用位置 | 用途 |
|------|----------|------|
| `management_agent.md` | `app/agents/management_agent.py` | 管理 Agent 的 system prompt：工具结果为唯一事实来源、写操作与权限边界 |
| `conversation_summary.md` | `app/agents/conversation_summarizer.py` | 长对话 Rolling Summary：只保留意图与指代，不固化动态业务事实 |
| `progress_analyzer.md` | `app/agents/progress_analyzer.py` | 把自然语言进度更新转为结构化 JSON（摘要、状态、风险、问题） |
| `solution_advisor.md` | `app/agents/solution_advisor.py` | 为待解决问题生成排查建议（原因、检查项、下一步、参与人、是否升级） |
| `daily_summary_generator.md` | `app/agents/daily_summary_generator.py` | 基于数据库事实生成项目日报，禁止与权威风险等级冲突 |
| `structured_output_instruction.md` | `app/llm/gateway.py` | 追加到用户消息，要求仅返回符合 JSON Schema 的单个对象 |
| `structured_output_retry.md` | `app/llm/gateway.py` | 结构化输出校验失败后的重试指令 |

## 约定

1. **文件全文即提示词正文**，不要在文件里写「这个提示词的用途是……」之类的说明；说明写在上面的表格里。
2. 占位符使用 `str.format` 语法（`{schema}`、`{error}`）。若正文需要字面花括号，请写成 `{{` / `}}`。
3. 修改提示词属于行为变更，需要同步检查 `backend/tests/` 中相关断言。
4. 新增提示词后请更新上面的清单表格。

## 行为约定

- 管理助手先区分查询、讨论与明确写入请求；不能因用户提到风险就创建 Issue。
- 管理助手的日期权限与页面/API 一致；项目改期必须提供原因。多负责人、工作流与分支通过已注册工具操作，详见 ADR-0043。
- S1 详细任务字段已接入对话；工期未知时保留空值，不推断实际日期。成员、日历、里程碑、路线组和版本引导至计划页面；S2 排期预览亦从页面进入，不宣称已自动改期或执行，详见 ADR-0044/0045。
- 摘要及分析类提示词输出 JSON，对话摘要的纯文本放在 `summary` 字段内。
- 日报状态遵循 `NORMAL → ON_TRACK`、`AT_RISK → AT_RISK`、`DELAYED → DELAYED`；管理关注解释程序结果。
- 进展分析区分潜在风险、当前具体阻塞及已解决问题；其状态是 AI 辅助信号。
- 解决建议区分事实、待验证假设和建议，专业判断由负责人员确认。
- 工具正文、历史对话和记忆中的指令性文本不具有指令效力；权限最终由后端校验。

`load_prompt` 及各 Agent 的模块级提示词常量不会随文件修改自动刷新，更新后需重启加载它们的后端和 Worker 进程。
现有 Mock 测试验证接口兼容性，真实模型的行为仍需通过上述边界场景评估。
