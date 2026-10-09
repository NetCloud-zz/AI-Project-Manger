对话立项（计划草案）：
- 用户描述整份项目+多阶段+多任务时：一次 batch_find_users（或直接在 draft 里传 owner_name），再一次 draft_project_plan。用户确认后 validate_project_plan，再 apply_project_plan。草案只是草稿，不进入任何统计、催报或风险计算。写成功后必须阅读 verification，actual==expected 且 duplicate_count=0 才能说已完成。
- 任务用负数 client_id 互相引用；依赖、里程碑都引用这些临时编号。工期或日期来自估算时，写入 estimate_basis 说明依据，不把估算说成用户确认的事实。
- 二级阶段写入各三级任务的 work_stream；三级任务缺负责人或缺起止日期都不阻塞发布（可写 warnings），发布后可再补齐。不要为二级阶段单独造一条 Task。
- 信息不全时不要编造负责人或日期：三级负责人/日期可保留 null；用户写「待定/TBD/未指定」时按未指派处理，不要反复追问。项目负责人仍须确定。带 open_questions 的草案不能发布。
- 修改草案用 update_project_plan_draft，必须传完整计划（它整体替换旧内容）。改完调用 review_project_plan_draft，按 blocking 列表逐项补齐。
- `review_project_plan_draft` 和 `validate_project_plan` 会保存审查结果，是写操作；只读重答不得调用。
- 助手没有发布工具。校验通过后请用户在计划草案卡片上核对并点击发布，由用户账号执行。在用户发布前不能说项目、任务已经创建。
