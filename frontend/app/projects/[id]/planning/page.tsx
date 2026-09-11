"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { App, Alert, Button, Checkbox, DatePicker, Form, Input, InputNumber, Modal, Select, Switch, Table, Tabs, Tag } from "antd";
import dayjs from "dayjs";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { ChangeProposalPanel } from "@/components/project/ChangeProposalPanel";
import { SchedulePreviewPanel } from "@/components/project/SchedulePreviewPanel";
import { ScheduleImpactModal } from "@/components/project/ScheduleImpactModal";
import { AppCard } from "@/components/common/AppCard";
import { LoadingState } from "@/components/feedback/LoadingState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { fetchAssignableUsers } from "@/services/projects";
import { updateTaskLink } from "@/services/gantt";
import type { TaskLinkType } from "@/types/gantt";
import { updateTask } from "@/services/tasks";
import { fetchParticipants, fetchPlanning, fetchPlanVersion, savePlanning } from "@/services/planning";
import type { PlanningContext, PlanVersion } from "@/types/planning";
import type { Task, TaskUpdateInput } from "@/types/task";
import { ApiError } from "@/lib/http";
import { scheduleImpactOf, type ScheduleImpact } from "@/lib/schedule-impact";

type Choice = { value: number; label: string };
type Editor = { kind: "link" | "task" | "member" | "participants" | "calendar" | "milestone" | "group" | "branch" | "option" | "selection" | "version"; id?: number; title: string };
type FormValues = Record<string, unknown>;
const linkLabels = { FINISH_TO_START: "完成后开始", START_TO_START: "开始后开始", FINISH_TO_FINISH: "完成后完成", START_TO_FINISH: "开始后完成" };
const dateKeys = ["start_date", "due_date", "target_date", "achieved_date", "actual_start_date", "actual_finish_date", "earliest_start_date", "fixed_start_date", "fixed_due_date"];
const text = (error: unknown) => {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload !== null && "detail" in error.payload) {
    const detail = error.payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => {
          if (!item || typeof item !== "object") return null;
          const row = item as { loc?: unknown[]; msg?: string };
          const where = Array.isArray(row.loc) ? row.loc.filter((part) => part !== "body").join(".") : "";
          return row.msg ? `${where ? `${where}: ` : ""}${row.msg}` : null;
        })
        .filter(Boolean);
      if (parts.length) return parts.join("；");
    }
  }
  return "保存失败，请检查输入或刷新后重试";
};
const pickerDate = (value: unknown) => {
  if (dayjs.isDayjs(value)) return value.format("YYYY-MM-DD");
  if (typeof value === "string" && value.trim()) {
    const parsed = dayjs(value);
    return parsed.isValid() ? parsed.format("YYYY-MM-DD") : null;
  }
  return null;
};

function PlanningPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);
  const linkedProposalId = useSearchParams().get("proposal");
  const { message } = App.useApp();
  const [data, setData] = useState<PlanningContext | null>(null);
  const [users, setUsers] = useState<Choice[]>([]);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [impact, setImpact] = useState<ScheduleImpact | null>(null);
  const [version, setVersion] = useState<PlanVersion | null>(null);
  const [form] = Form.useForm<FormValues>();
  const [proposalRefresh, setProposalRefresh] = useState(0);
  const [activeTab, setActiveTab] = useState<string>();
  const reload = useCallback(async () => {
    const next = await fetchPlanning(projectId);
    setData(next);
    setFailed(false);
    if (next.editable) {
      const candidates = await fetchAssignableUsers(projectId);
      setUsers(candidates.map(u => ({ value: u.id, label: `${u.name} (${u.username})` })));
    }
  }, [projectId]);
  useEffect(() => { let alive = true; fetchPlanning(projectId).then(async next => {
    if (!alive) return;
    setData(next);
    if (next.editable) {
      const candidates = await fetchAssignableUsers(projectId);
      if (alive) setUsers(candidates.map(u => ({ value: u.id, label: `${u.name} (${u.username})` })));
    }
  }).catch(() => { if (alive) setFailed(true); }); return () => { alive = false; }; }, [projectId]);

  const open = (next: Editor, values: FormValues = {}) => {
    form.resetFields();
    const prepared = { ...values };
    for (const key of dateKeys) if (typeof prepared[key] === "string") prepared[key] = dayjs(prepared[key] as string);
    form.setFieldsValue(prepared);
    setEditor(next);
  };
  const save = async (values: FormValues) => {
    if (!editor || !data) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { ...values };
      for (const key of dateKeys) if (key in body) body[key] = pickerDate(body[key]);
      let path = "", method = "POST";
      switch (editor.kind) {
        case "task": {
          const original = data.tasks.find(t => t.id === editor.id)!;
          const patch: Record<string, unknown> = {};
          for (const [key, value] of Object.entries(body)) {
            const normalized = value === undefined || value === "" ? null : value;
            if (normalized !== (original[key as keyof typeof original] ?? null)) patch[key] = normalized;
          }
          await updateTask(editor.id!, patch as TaskUpdateInput);
          break;
        }
        case "link": await updateTaskLink(editor.id!, body.link_type as TaskLinkType, Number(body.lag_days)); break;
        case "member": path = `members/${body.user_id}`; delete body.user_id; method = "PUT"; break;
        case "participants": {
          path = `tasks/${editor.id}/participants`; method = "PUT";
          body.participants = [
            ...((body.collaborators as number[]) ?? []).map(user_id => ({ user_id, role: "COLLABORATOR" })),
            ...((body.watchers as number[]) ?? []).map(user_id => ({ user_id, role: "WATCHER" })),
          ];
          delete body.collaborators; delete body.watchers; break;
        }
        case "calendar": {
          // Planning schemas use extra=forbid. Build a whitelist payload so leftover
          // fields from a previous editor (Form preserve) cannot trigger HTTP 422.
          path = "calendar";
          method = "PUT";
          const exceptions: Record<string, boolean> = {};
          for (const item of (body.exception_rows as { date: unknown; working?: boolean }[] ?? [])) {
            const date = pickerDate(item.date);
            if (!date) throw new Error("Missing date");
            if (date in exceptions) { message.error("例外日期不能重复"); setBusy(false); return; }
            exceptions[date] = Boolean(item.working);
          }
          const weekdays = Array.isArray(body.weekdays)
            ? [...new Set((body.weekdays as unknown[]).map((day) => Number(day)))]
            : [];
          const calendarBody = {
            name: String(body.name ?? "").trim(),
            timezone: String(body.timezone ?? "Asia/Shanghai").trim(),
            weekdays,
            exceptions,
            expected_version: data.calendar.version,
            reason: String(body.reason ?? "").trim(),
          };
          await savePlanning(projectId, path, calendarBody, method);
          path = "";
          break;
        }
        case "milestone": path = `milestones${editor.id ? `/${editor.id}` : ""}`; method = editor.id ? "PUT" : "POST"; break;
        case "group": path = `task-groups${editor.id ? `/${editor.id}` : ""}`; method = editor.id ? "PUT" : "POST"; break;
        case "branch": path = `branch-groups${editor.id ? `/${editor.id}` : ""}`; method = editor.id ? "PUT" : "POST"; break;
        case "option": path = `branch-groups/${editor.id}/options`; break;
        case "selection": path = `branch-groups/${editor.id}/select`; body.expected_selected_option_id = data.branch_options.find(o => o.group_id === editor.id && o.is_selected)?.id ?? null; break;
        case "version": path = "versions"; body.expected_latest_version = data.versions[0]?.version ?? 0; break;
      }
      if (path) await savePlanning(projectId, path, body, method);
      message.success("已保存"); setEditor(null); await reload();
    } catch (error) {
      // A refusal because other tasks would move is not a failure to report;
      // it is a redirect to the flow that can show the whole difference.
      const ripple = scheduleImpactOf(error);
      if (ripple) { setImpact(ripple); setEditor(null); } else { message.error(text(error)); }
    } finally { setBusy(false); }
  };
  if (failed) return <PageContainer><ErrorState description="无法加载计划资料" onRetry={() => { void reload().catch(() => setFailed(true)); }} /></PageContainer>;
  if (!data) return <PageContainer><LoadingState tip="加载计划资料…" /></PageContainer>;
  const taskChoices = data.tasks.map(t => ({ value: t.id, label: `${t.task_name} (#${t.id})` }));
  const memberChoices = data.members.filter(m => m.is_active).map(m => ({ value: m.user_id, label: m.user_name }));
  const editButton = (next: Editor, values: FormValues = {}) => data.editable ? <Button onClick={() => open(next, values)}>{next.title}</Button> : null;
  const input = (name: string, label: string, required = false) => <Form.Item name={name} label={label} rules={required ? [{ required: true, whitespace: true }] : undefined}><Input /></Form.Item>;
  const dateInput = (name: string, label: string, required = false) => <Form.Item name={name} label={label} rules={required ? [{ required: true }] : undefined}><DatePicker className="full-width" /></Form.Item>;
  const selectInput = (name: string, label: string, options: Choice[], multiple = false, required = false) => <Form.Item name={name} label={label} rules={required ? [{ required: true }] : undefined}><Select allowClear showSearch optionFilterProp="label" mode={multiple ? "multiple" : undefined} options={options} /></Form.Item>;
  const reason = input("reason", "变更原因", true);
  const loadParticipants = async (taskId: number) => {
    try {
      const participants = await fetchParticipants(projectId, taskId);
      open({ kind: "participants", id: taskId, title: "协作者与关注人" }, {
        collaborators: participants.filter(p => p.role === "COLLABORATOR").map(p => p.user_id),
        watchers: participants.filter(p => p.role === "WATCHER").map(p => p.user_id),
      });
    } catch { message.error("读取协作关系失败"); }
  };

  return <PageContainer>
    <PageHeader title="计划资料与路线" subtitle="维护执行依据，保存可追溯的计划版本" backHref={`/projects/${projectId}`} backLabel="项目详情" />
    {!data.full_access && <Alert type="info" title="仅展示你有权访问的任务。项目成员资格不会开放全部任务或计划历史。" />}
    <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
      { key: "proposals", label: "变更方案", children: <ChangeProposalPanel projectId={projectId} data={data} users={users} refreshKey={proposalRefresh} initialProposalId={linkedProposalId} onApplied={reload} /> },
      { key: "schedule", label: "排期预览", children: <SchedulePreviewPanel projectId={projectId} data={data} onProposalCreated={() => setProposalRefresh(value => value + 1)} /> },
      { key: "tasks", label: "任务资料", children: <AppCard>
        <Table rowKey="id" dataSource={data.tasks} scroll={{ x: 800 }} columns={[
          { title: "任务", dataIndex: "task_name" },
          { title: "计划 / 剩余工期", render: (_, t) => `${t.planned_duration_days ?? "待补全"} / ${t.remaining_duration_days ?? "待补全"} 工作日` },
          { title: "交付物", dataIndex: "deliverable" },
          { title: "路线", render: (_, t) => t.is_active_branch ? <Tag color="green">当前</Tag> : <Tag>备用 / 历史</Tag> },
          { title: "操作", render: (_, t) => editButton({ kind: "task", id: t.id, title: "编辑资料" }, { ...t }) },
        ]} />
      </AppCard> },
      { key: "links", label: "依赖间隔", children: <AppCard>
        <p>依赖连线在甘特图中维护；此处设置类型与等待工作日。保存后不会自动重排任务。</p>
        <Table rowKey="id" dataSource={data.links} columns={[
          { title: "前置任务", render: (_, link) => data.tasks.find(t => t.id === link.source_id)?.task_name },
          { title: "后续任务", render: (_, link) => data.tasks.find(t => t.id === link.target_id)?.task_name },
          { title: "类型", render: (_, link) => linkLabels[link.link_type as TaskLinkType] },
          { title: "等待工作日", dataIndex: "lag_days" },
          { title: "操作", render: (_, link) => editButton({ kind: "link", id: link.id, title: "编辑间隔" }, { link_type: link.link_type, lag_days: link.lag_days }) },
        ]} />
      </AppCard> },
      { key: "members", label: "成员与协作", children: <AppCard>
        {editButton({ kind: "member", title: "添加成员" }, { role: "CONTRIBUTOR", receive_notifications: true, is_active: true })}
        <Table rowKey="user_id" dataSource={data.members} columns={[
          { title: "成员", dataIndex: "user_name" }, { title: "角色", render: (_, m) => m.role === "OBSERVER" ? "观察者" : "参与者" },
          { title: "状态", render: (_, m) => m.is_active ? "有效" : "已停用" },
          { title: "通知偏好", render: (_, m) => m.receive_notifications ? "接收" : "不接收" },
          { title: "操作", render: (_, m) => editButton({ kind: "member", title: "编辑成员" }, { user_id: m.user_id, role: m.role, is_active: m.is_active, receive_notifications: m.receive_notifications }) },
        ]} />
        <p className="meta-line">共同负责人仍在项目管理中维护。协作者和关注人获得指定任务的查看权限；任务负责人继续负责汇报。通知偏好将在通知阶段接入。</p>
        {data.editable && <Select className="full-width" placeholder="选择任务，维护协作关系" value={null} options={taskChoices} onChange={value => { if (value != null) void loadParticipants(value); }} />}
      </AppCard> },
      { key: "milestones", label: "里程碑与任务组", children: <AppCard>
        {editButton({ kind: "milestone", title: "新增里程碑" }, { status: "PLANNED" })}
        <Table rowKey="id" dataSource={data.milestones} columns={[
          { title: "里程碑", dataIndex: "name" }, { title: "目标日期", dataIndex: "target_date" },
          { title: "交付物", dataIndex: "deliverable" },
          { title: "状态", render: (_, m) => ({ PLANNED: "计划中", ACHIEVED: "已达成", CANCELLED: "已取消" })[m.status] },
          { title: "操作", render: (_, m) => editButton({ kind: "milestone", id: m.id, title: "编辑" }, { name: m.name, deliverable: m.deliverable, acceptance_criteria: m.acceptance_criteria, target_date: m.target_date, owner_id: m.owner_id, status: m.status, achieved_date: m.achieved_date }) },
        ]} />
        {editButton({ kind: "group", title: "新增任务组" })}
        <Table rowKey="id" dataSource={data.task_groups} columns={[
          { title: "任务组", dataIndex: "name" }, { title: "父组", render: (_, g) => data.task_groups.find(p => p.id === g.parent_id)?.name ?? "无" },
          { title: "操作", render: (_, g) => editButton({ kind: "group", id: g.id, title: "编辑" }, { name: g.name, parent_id: g.parent_id }) },
        ]} />
      </AppCard> },
      { key: "calendar", label: "工作日历", children: <AppCard>
        <p>{data.calendar.name} · 版本 {data.calendar.version} · {data.calendar.timezone}</p>
        <p>每周工作日：{data.calendar.weekdays.map(d => ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d]).join("、")}</p>
        <p>工期以整数工作日计；例外日覆盖周规则。日历不自动包含法定节假日，保存后不会自动改变任务日期。</p>
        {editButton({ kind: "calendar", title: "编辑日历" }, { name: data.calendar.name, timezone: data.calendar.timezone, weekdays: data.calendar.weekdays, exception_rows: Object.entries(data.calendar.exceptions).map(([date, working]) => ({ date: dayjs(date), working })) })}
        <Table rowKey="date" dataSource={Object.entries(data.calendar.exceptions).map(([date, working]) => ({ date, working }))} columns={[{ title: "例外日期", dataIndex: "date" }, { title: "安排", render: (_, r) => r.working ? "工作日" : "休息日" }]} />
      </AppCard> },
      { key: "branches", label: "替代路线", children: <AppCard>
        <Alert type="info" title="路线切换须先预览依赖与日期影响，保存变更方案，经差异核对和确认后执行。" />
        {editButton({ kind: "branch", title: "新增路线组" })}
        {data.branch_groups.map(group => <AppCard key={group.id}>
          <h3>{group.name}</h3>
          {editButton({ kind: "branch", id: group.id, title: "编辑入口与汇合" }, { name: group.name, entry_task_id: group.entry_task_id, exit_task_id: group.exit_task_id })}
          <p className="meta-line">入口：{data.tasks.find(t => t.id === group.entry_task_id)?.task_name ?? "未设置"} · 汇合：{data.tasks.find(t => t.id === group.exit_task_id)?.task_name ?? "未设置"}</p>
          {editButton({ kind: "option", id: group.id, title: "添加备用选项" })}
          {data.editable && <Button onClick={() => setActiveTab("schedule")}>预览路线切换</Button>}
          {data.branch_options.filter(o => o.group_id === group.id).map(option => <p key={option.id}>
            <Tag color={option.is_selected ? "green" : undefined}>{option.is_selected ? "当前" : "备用 / 历史"}</Tag>{option.name}：{option.task_ids.map(taskId => data.tasks.find(t => t.id === taskId)?.task_name ?? `#${taskId}`).join("、")}
          </p>)}
        </AppCard>)}
      </AppCard> },
      { key: "versions", label: "计划版本", children: <AppCard>
        <p>版本保存当前计划快照，保存后不可编辑；迁移基准不代表原始立项计划。</p>
        {editButton({ kind: "version", title: "保存计划版本" })}
        <Table rowKey="id" dataSource={data.versions} columns={[
          { title: "版本", dataIndex: "version" }, { title: "类型", render: (_, v) => v.kind === "MIGRATION_BASELINE" ? "迁移基准" : v.kind === "BASELINE" ? "首次基准" : "计划快照" },
          { title: "原因", dataIndex: "reason" }, { title: "保存时间", render: (_, v) => dayjs(v.created_at).format("YYYY-MM-DD HH:mm") },
          { title: "详情", render: (_, v) => <Button onClick={() => { fetchPlanVersion(projectId, v.id).then(setVersion).catch(() => message.error("读取版本失败")); }}>查看</Button> },
        ]} />
      </AppCard> },
    ].filter(tab => data.full_access || ["tasks", "members", "calendar"].includes(tab.key))} />

    <ScheduleImpactModal projectId={projectId} impact={impact} onClose={() => setImpact(null)} onOpenPreview={() => setActiveTab("schedule")} />

    <Modal title={editor?.title} open={Boolean(editor)} onCancel={() => setEditor(null)} onOk={() => form.submit()} confirmLoading={busy} destroyOnHidden width={720}>
      <Form form={form} layout="vertical" onFinish={save} preserve={false}>
        {editor?.kind === "task" && <>
          {input("description", "任务说明")}{input("deliverable", "交付物")}{input("acceptance_criteria", "验收条件")}
          <Form.Item name="planned_duration_days" label="计划工期（工作日，未知可留空）"><InputNumber min={1} max={10000} precision={0} /></Form.Item>
          <Form.Item name="remaining_duration_days" label="剩余工期（工作日）"><InputNumber min={0} max={10000} precision={0} /></Form.Item>
          {dateInput("start_date", "当前计划开始")}{dateInput("due_date", "当前计划截止")}
          {dateInput("earliest_start_date", "不得早于")}{dateInput("fixed_start_date", "固定开始（须等于当前开始日期）")}{dateInput("fixed_due_date", "固定截止（须等于当前截止日期）")}
          {dateInput("actual_start_date", "实际开始")}{dateInput("actual_finish_date", "实际完成（仅已完成任务可填）")}
          {selectInput("milestone_id", "关联里程碑", data.milestones.map(m => ({ value: m.id, label: m.name })))}
          {selectInput("task_group_id", "所属任务组", data.task_groups.map(g => ({ value: g.id, label: g.name })))}
        </>}
        {editor?.kind === "link" && <>
          <Form.Item name="link_type" label="依赖类型" rules={[{ required: true }]}><Select options={Object.entries(linkLabels).map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Form.Item name="lag_days" label="等待工作日" rules={[{ required: true }]}><InputNumber min={0} max={10000} precision={0} /></Form.Item>
        </>}
        {editor?.kind === "member" && <>
          {selectInput("user_id", "人员", users, false, true)}
          <Form.Item name="role" label="项目角色" rules={[{ required: true }]}><Select options={[{ value: "CONTRIBUTOR", label: "参与者" }, { value: "OBSERVER", label: "观察者" }]} /></Form.Item>
          <Form.Item name="is_active" label="成员有效" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="receive_notifications" label="接收通知（偏好）" valuePropName="checked"><Switch /></Form.Item>
        </>}
        {editor?.kind === "participants" && <>{selectInput("collaborators", "协作者", memberChoices, true)}{selectInput("watchers", "关注人", memberChoices, true)}</>}
        {editor?.kind === "milestone" && <>
          {input("name", "里程碑名称", true)}{input("deliverable", "交付物")}{input("acceptance_criteria", "验收条件")}
          {dateInput("target_date", "目标日期")}{selectInput("owner_id", "负责人", users)}
          <Form.Item name="status" label="状态" rules={[{ required: true }]}><Select options={[{ value: "PLANNED", label: "计划中" }, { value: "ACHIEVED", label: "已达成" }, { value: "CANCELLED", label: "已取消" }]} /></Form.Item>
          {dateInput("achieved_date", "实际达成日期（已达成时必填）")}
        </>}
        {editor?.kind === "group" && <>{input("name", "任务组名称", true)}{selectInput("parent_id", "父任务组", data.task_groups.filter(g => g.id !== editor.id).map(g => ({ value: g.id, label: g.name })))}</>}
        {editor?.kind === "calendar" && <>
          {input("name", "日历名称", true)}{input("timezone", "时区（如 Asia/Shanghai）", true)}
          <Form.Item name="weekdays" label="常规工作日" rules={[{ required: true }]}><Checkbox.Group options={["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((label, value) => ({ label, value }))} /></Form.Item>
          <Form.List name="exception_rows">{(fields, { add, remove }) => <>
            {fields.map(field => <div key={field.key} className="chip-row">
              <Form.Item name={[field.name, "date"]} rules={[{ required: true }]}><DatePicker /></Form.Item>
              <Form.Item name={[field.name, "working"]} valuePropName="checked"><Switch checkedChildren="工作" unCheckedChildren="休息" /></Form.Item>
              <Button onClick={() => remove(field.name)}>移除例外日</Button>
            </div>)}<Button onClick={() => add({ working: false })}>添加例外日期</Button>
          </>}</Form.List>{reason}
        </>}
        {editor?.kind === "branch" && <>{input("name", "路线组名称", true)}{selectInput("entry_task_id", "共享入口", taskChoices)}{selectInput("exit_task_id", "公共汇合任务", taskChoices)}{editor.id && reason}</>}
        {editor?.kind === "option" && <>
          <Alert type="warning" title="加入选项后，所选任务将成为备用任务，直到该选项被选中。" />
          {input("name", "选项名称", true)}
          {selectInput("task_ids", "纳入的未开始任务", data.tasks.filter(t => t.status === "TODO" && !t.branch_option_id && !t.branch_root_id).map(t => ({ value: t.id, label: t.task_name })), true, true)}{reason}
        </>}
        {editor?.kind === "selection" && <>{selectInput("option_id", "执行选项", data.branch_options.filter(o => o.group_id === editor.id).map(o => ({ value: o.id, label: o.name })), false, true)}{reason}</>}
        {editor?.kind === "version" && reason}
      </Form>
    </Modal>
    <Modal title={`计划版本 ${version?.version ?? ""}`} open={Boolean(version)} onCancel={() => setVersion(null)} footer={null} width={900}>
      <p>{version?.reason}</p>
      <Table rowKey="id" scroll={{ x: 700 }} dataSource={(version?.snapshot?.tasks as Task[] | undefined) ?? []} columns={[
        { title: "任务", dataIndex: "task_name" }, { title: "开始", dataIndex: "start_date" }, { title: "截止", dataIndex: "due_date" },
        { title: "计划工期", render: (_, task) => task.planned_duration_days == null ? "待补全" : `${task.planned_duration_days} 工作日` },
        { title: "交付物", dataIndex: "deliverable" }, { title: "路线", render: (_, task) => task.is_active_branch ? "当时选中" : "备用 / 历史" },
      ]} />
    </Modal>
  </PageContainer>;
}
export default function Page() {
  return <RequireAuth>
    <Suspense fallback={<PageContainer><LoadingState tip="加载计划资料…" /></PageContainer>}>
      <PlanningPage />
    </Suspense>
  </RequireAuth>;
}
