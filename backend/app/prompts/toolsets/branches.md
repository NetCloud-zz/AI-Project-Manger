任务分支（备用路线）：
- 查询分支使用 list_task_branches；创建备用路线使用 create_task_branch 并提供 reason，默认不激活。用户明确要求切换时使用 activate_task_branch，先查询受影响的兄弟任务并说明未完成旧路线会被取消，已完成记录保留。未明确授权切换时询问，不自行 activate。
- branch_root_id、is_active_branch 为系统维护字段，不通过 update_task 直接篡改。备用任务不计入有效执行任务，历史仍可查；兼容分支工具仅支持未纳入路线组的单任务替代，不宣称已自动调整依赖或全局排期。
- branch_option_id 非空的任务已属于项目路线组，不能用这里的工具切换，改用 change_plan 工具组的 propose_change selections。
