兼容查询工具：
- query_tasks 是任务专用的查询 DSL，能力与 query_entities(entity=task) 重叠；只在 query_entities 无法表达时使用。
- list_projects 列出可见项目；按名称或编号查找优先 search_projects / get_project。
- list_project_tasks 列出单个项目的任务；需要筛选状态、负责人或日期时用 search_tasks。
