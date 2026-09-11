"use client";

import { useEffect, useState } from "react";
import { Alert, App, Button, Checkbox, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tag } from "antd";
import dayjs from "dayjs";
import { AppCard } from "@/components/common/AppCard";
import { NotificationStatusCard } from "@/components/agent/NotificationStatusCard";
import { useAuth } from "@/components/providers/AuthProvider";
import { ApiError } from "@/lib/http";
import { createProposal, editProposal, getProposal, listProposals, proposalAction } from "@/services/change-proposals";
import type { ChangeProposal } from "@/types/change-proposal";
import type { PlanningContext } from "@/types/planning";

const labels = { DRAFT: "草案", VALIDATED: "已验证，待核对", CONFIRMED: "已确认，待执行", APPLIED: "已执行", REJECTED: "已拒绝", EXPIRED: "已过期", FAILED: "执行失败" };
const fields: Record<string, string> = { task_name: "任务名称", owner_id: "负责人", work_stream: "工作流", description: "说明", deliverable: "交付物", acceptance_criteria: "验收条件", planned_duration_days: "计划工作日", remaining_duration_days: "剩余工作日", start_date: "开始日期", due_date: "截止日期", earliest_start_date: "最早开始", fixed_start_date: "固定开始", fixed_due_date: "固定截止", calendar_id: "工作日历", milestone_id: "里程碑", task_group_id: "任务组", progress_percent: "进度", status: "任务状态", is_active_branch: "执行路线" };
const linkLabels: Record<string, string> = { FINISH_TO_START: "完成后开始", START_TO_START: "开始后开始", FINISH_TO_FINISH: "完成后完成", START_TO_FINISH: "开始后完成" };
const display = (value: unknown) => value == null || value === "" ? "未设置" : value === true ? "当前" : value === false ? "备用 / 历史" : String(value);
const errorText = (error: unknown) => error instanceof ApiError && typeof error.payload === "object" && error.payload !== null && "detail" in error.payload && typeof error.payload.detail === "string" ? error.payload.detail : "操作未确认，请刷新方案核实后重试";
const dates = ["start_date", "due_date", "earliest_start_date", "fixed_start_date", "fixed_due_date"];
function prepare(row: Record<string, unknown>) {
  const result = { ...row };
  for (const key of dates) if (typeof result[key] === "string") result[key] = dayjs(result[key] as string);
  return result;
}
function serialize(row: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(row).filter(([, value]) => value !== undefined).map(([key, value]) => [key, dayjs.isDayjs(value) ? value.format("YYYY-MM-DD") : value === "" ? null : value]));
}

export function ChangeProposalPanel({ projectId, data, users, refreshKey, initialProposalId, onApplied }: { projectId: number; data: PlanningContext; users: { value: number; label: string }[]; refreshKey: number; initialProposalId?: string | null; onApplied: () => Promise<void> }) {
  const { user } = useAuth();
  const { message } = App.useApp();
  const [rows, setRows] = useState<ChangeProposal[]>([]);
  const [selected, setSelected] = useState<ChangeProposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState<{ key: string; reason: string } | null>(null);
  const [form] = Form.useForm();
  const newTasks = Form.useWatch("new_tasks", form) as { client_id: number; task: Record<string, unknown> }[] | undefined;
  const targetOverride = Form.useWatch("override_target", form);
  useEffect(() => {
    let alive = true;
    listProposals(projectId).then(result => { if (alive) { setRows(result); setFailed(false); } }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [projectId, refreshKey]);
  const refresh = async () => { try { setRows(await listProposals(projectId)); setFailed(false); } catch { setFailed(true); } };
  const open = async (id: string) => {
    try { setSelected(await getProposal(projectId, id)); setReviewed(false); } catch (error) { message.error(errorText(error)); }
  };
  // A card in the assistant conversation links straight to one proposal.
  useEffect(() => {
    if (!initialProposalId) return;
    let alive = true;
    getProposal(projectId, initialProposalId)
      .then(row => { if (alive) { setSelected(row); setReviewed(false); } })
      .catch(() => { if (alive) message.error("无法打开该变更方案"); });
    return () => { alive = false; };
  }, [initialProposalId, projectId, message]);
  const run = async (action: string) => {
    if (!selected) return;
    setBusy(true);
    try {
      const next = await proposalAction(projectId, selected.id, action, {
        expected_revision: selected.revision,
        ...(["confirm", "apply", "compensate"].includes(action) ? { digest: selected.digest } : {}),
        ...(["apply", "compensate"].includes(action) ? { idempotency_key: `${action}:${selected.id}:${selected.revision}:${user?.id}` } : {}),
      });
      setSelected(next); setReviewed(false); await refresh();
      if (next.status === "APPLIED") { message.success("方案已执行，待发送通知事件已保存"); await onApplied(); }
      else if (["FAILED", "EXPIRED"].includes(next.status)) message.warning(next.failure_reason ?? labels[next.status]);
      else message.success(labels[next.status]);
    } catch (error) { message.error(errorText(error)); } finally { setBusy(false); }
  };
  const createDraft = async () => {
    if (!draft || draft.reason.trim().length < 2) return;
    setBusy(true);
    try {
      const next = await createProposal(projectId, { reason: draft.reason, change: {}, idempotency_key: draft.key });
      setSelected(next); setDraft(null); setReviewed(false); await refresh();
      message.success("草案已创建，请编辑任务及依赖后验证");
    } catch (error) { message.error(errorText(error)); } finally { setBusy(false); }
  };
  const startEdit = () => {
    if (!selected) return;
    form.resetFields();
    form.setFieldsValue({ reason: selected.reason, mode: selected.request.mode ?? "preserve_dates", changes: (selected.request.changes ?? []).map(prepare), new_tasks: (selected.request.new_tasks ?? []).map(item => ({ ...item, task: prepare(item.task) })), links: selected.request.links ?? data.links.map(({ source_id, target_id, link_type, lag_days }) => ({ source_id, target_id, link_type, lag_days })), selections: selected.request.selections ?? [], override_target: "project_target_date" in selected.request, target_date: selected.request.project_target_date ? dayjs(String(selected.request.project_target_date)) : null });
    setEditing(true);
  };
  const save = async (values: Record<string, unknown>) => {
    if (!selected) return;
    setBusy(true);
    try {
      const change = { ...selected.request };
      delete change.as_of; delete change.expected_snapshot_token; delete change.project_target_date;
      change.mode = values.mode;
      change.changes = ((values.changes as Record<string, unknown>[]) ?? []).map(serialize);
      change.new_tasks = ((values.new_tasks as { client_id: number; task: Record<string, unknown> }[]) ?? []).map(item => ({ ...item, task: serialize(item.task) }));
      change.links = values.links as typeof change.links;

      if (values.override_target) change.project_target_date = dayjs.isDayjs(values.target_date) ? values.target_date.format("YYYY-MM-DD") : null;
      const next = await editProposal(projectId, selected.id, { expected_revision: selected.revision, reason: values.reason, change });
      setSelected(next); setEditing(false); setReviewed(false); await refresh();
      message.success("已保存新草案，旧确认已清除，请重新验证");
    } catch (error) { message.error(errorText(error)); } finally { setBusy(false); }
  };
  const taskName = (id: number) => selected?.diff?.tasks.find(task => task.task_id === id)?.after.task_name as string | undefined ?? data.tasks.find(task => task.id === id)?.task_name ?? `#${id}`;
  const taskChoices = [...data.tasks.map(task => ({ value: task.id, label: task.task_name })), ...(newTasks ?? []).map(item => ({ value: item.client_id, label: String(item.task?.task_name ?? "新增任务") }))];
  const person = (id: number) => users.find(user => user.value === id)?.label ?? data.members.find(member => member.user_id === id)?.user_name ?? `人员 #${id}`;
  const diff = selected?.diff;

  return <AppCard>
    <p>从“排期预览”保存方案，再核对完整差异、确认并执行。确认后编辑会清除旧确认；只有“已执行”表示计划已保存。</p>
    <Space><Button onClick={() => void refresh()}>刷新方案列表</Button>{data.editable && <Button onClick={() => setDraft({ key: crypto.randomUUID(), reason: "" })}>新建草案</Button>}</Space>
    <Modal open={Boolean(draft)} title="新建变更草案" onCancel={() => setDraft(null)} onOk={() => void createDraft()} confirmLoading={busy} okButtonProps={{ disabled: !draft || draft.reason.trim().length < 2 }}>
      <Input.TextArea placeholder="变更原因（至少两个字）" value={draft?.reason} onChange={event => setDraft(current => current ? { ...current, reason: event.target.value } : current)} />
    </Modal>
    {failed && <Alert type="error" title="读取方案失败，请刷新重试" />}
    <div className="proposal-table-scroll">
      <Table
        rowKey="id"
        dataSource={rows}
        scroll={{ x: 640 }}
        columns={[
          { title: "变更原因", dataIndex: "reason", ellipsis: true, width: 220 },
          { title: "版本", dataIndex: "revision", width: 72 },
          { title: "状态", width: 120, render: (_, row) => <Tag>{labels[row.status]}</Tag> },
          { title: "创建时间", width: 140, render: (_, row) => dayjs(row.created_at).format("YYYY-MM-DD HH:mm") },
          { title: "操作", width: 120, fixed: "right", render: (_, row) => <Button onClick={() => void open(row.id)}>查看与处理</Button> },
        ]}
      />
    </div>
    <Modal open={Boolean(selected)} title={`变更方案 · 第 ${selected?.revision ?? ""} 版`} footer={null} onCancel={() => { if (!busy) setSelected(null); }} width={1100}>
      {selected && <>
        <p><Tag>{labels[selected.status]}</Tag>{selected.reason}</p>
        {selected.failure_reason && <Alert type="warning" title={selected.failure_reason} />}
        {selected.preview?.candidate.conflicts.map((issue, index) => <Alert key={index} type="error" title={issue.message} description={issue.suggestion} />)}
        <p>候选预测完成：{selected.preview?.candidate.project_finish_date ?? "尚未验证 / 无法确定"}</p>
        {diff && <>
          <Table rowKey="task_id" pagination={false} dataSource={diff.tasks} columns={[
            { title: "任务", render: (_, task) => String(task.after.task_name) },
            { title: "变更", render: (_, task) => task.before ? "修改" : "新增" },
            { title: "完整字段差异", render: (_, task) => Object.entries(fields).filter(([key]) => task.after[key] !== task.before?.[key] && (task.before != null || task.after[key] != null)).map(([key, label]) => <p key={key}>{label}：{key === "owner_id" ? (task.before?.[key] != null ? person(Number(task.before[key])) : "待定") : display(task.before?.[key])} → {key === "owner_id" ? (task.after[key] != null ? person(Number(task.after[key])) : "待定") : display(task.after[key])}</p>) },
          ]} />
          {diff.project && <p>项目目标：{display(diff.project.before.target_date)} → {display(diff.project.after.target_date)}</p>}
          <h4>依赖关系：变更前 / 变更后</h4>
          {(["before", "after"] as const).map(side => <div key={side}><strong>{side === "before" ? "变更前" : "变更后"}</strong>{diff.links[side].length ? diff.links[side].map(link => <p key={`${link.source_id}-${link.target_id}`}>{taskName(link.source_id)} → {taskName(link.target_id)} · {linkLabels[link.link_type]} · 等待 {link.lag_days} 工作日</p>) : <p>无依赖</p>}</div>)}
          {diff.selections.map(selection => <p key={selection.group_id}>路线 {data.branch_groups.find(group => group.id === selection.group_id)?.name}：{data.branch_options.find(option => option.id === selection.before_option_id)?.name ?? "未选择"} → {data.branch_options.find(option => option.id === selection.after_option_id)?.name}</p>)}
          <h4>通知对象（只记录待发送事件）</h4>
          {diff.notifications.map(recipient => <p key={recipient.user_id}>{person(recipient.user_id)}：{recipient.task_ids.map(taskName).join("、") || "项目变更"}</p>)}
        </>}
        {selected.status === "APPLIED" && data.editable && <Button loading={busy} onClick={() => void run("compensate")}>生成补偿草案</Button>}
        {selected.status === "APPLIED" && <Alert type="success" title={`计划已保存为版本记录 #${selected.applied_version_id}。再次读取或重试不会重复执行。`} />}
        {selected.status === "APPLIED" && <NotificationStatusCard projectId={projectId} proposalId={selected.id} />}
        {data.editable && <Space wrap>
          {!["APPLIED", "REJECTED"].includes(selected.status) && <Button disabled={busy} onClick={startEdit}>编辑草案</Button>}
          {["DRAFT", "VALIDATED", "FAILED"].includes(selected.status) && <Button loading={busy} onClick={() => void run("validate")}>重新验证</Button>}
          {selected.status === "VALIDATED" && <><Checkbox checked={reviewed} onChange={event => setReviewed(event.target.checked)}>已核对全部任务、依赖、路线、目标及通知对象</Checkbox><Button type="primary" disabled={!reviewed || busy} onClick={() => void run("confirm")}>确认此版本</Button></>}
          {selected.status === "CONFIRMED" && <Button type="primary" disabled={selected.confirmed_by !== user?.id} loading={busy} onClick={() => void run("apply")}>执行已确认方案</Button>}
          {!["APPLIED", "REJECTED"].includes(selected.status) && <Button danger disabled={busy} onClick={() => void run("reject")}>拒绝方案</Button>}
        </Space>}
      </>}
    </Modal>
    <Modal open={editing} title="编辑草案（保存后需重新验证与确认）" onCancel={() => setEditing(false)} onOk={() => form.submit()} confirmLoading={busy} width={950}>
      <Form form={form} layout="vertical" onFinish={save} preserve={false}>
        <Form.Item name="reason" label="变更原因" rules={[{ required: true, min: 2 }]}><Input.TextArea /></Form.Item>
        <Form.Item name="mode" label="排期方式"><Select options={[{ value: "preserve_dates", label: "保留当前安排" }, { value: "earliest", label: "最早可行方案" }]} /></Form.Item>
        <h4>现有任务变更</h4>
        <Form.List name="changes">{(items, { add, remove }) => <>{items.map(item => <AppCard key={item.key}>
          <Form.Item name={[item.name, "task_id"]} label="任务" rules={[{ required: true }]}><Select options={data.tasks.filter(task => task.status !== "COMPLETED").map(task => ({ value: task.id, label: task.task_name }))} /></Form.Item>
          <Space wrap><Form.Item name={[item.name, "planned_duration_days"]} label="计划工期"><InputNumber min={1} max={10000} precision={0} /></Form.Item><Form.Item name={[item.name, "remaining_duration_days"]} label="剩余工期"><InputNumber min={0} max={10000} precision={0} /></Form.Item><Form.Item name={[item.name, "owner_id"]} label="负责人"><Select allowClear style={{ width: 200 }} options={users} /></Form.Item></Space>
          <Space wrap>{dates.map(key => <Form.Item key={key} name={[item.name, key]} label={fields[key]}><DatePicker /></Form.Item>)}</Space>
          {["task_name", "description", "deliverable", "acceptance_criteria", "work_stream"].map(key => <Form.Item key={key} name={[item.name, key]} label={fields[key]}><Input /></Form.Item>)}
          <Button onClick={() => remove(item.name)}>移除变更</Button>
        </AppCard>)}<Button onClick={() => add()}>添加任务变更</Button></>}</Form.List>
        <h4>新增任务</h4>
        <Form.List name="new_tasks">{(items, { add, remove }) => <>{items.map(item => <AppCard key={item.key}>
          <Form.Item name={[item.name, "client_id"]} hidden><InputNumber /></Form.Item>
          <Form.Item name={[item.name, "task", "task_name"]} label="任务名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name={[item.name, "task", "owner_id"]} label="负责人" extra="可留空，表示待定">
            <Select allowClear placeholder="待定" options={users} />
          </Form.Item>
          <Space wrap><Form.Item name={[item.name, "task", "start_date"]} label="计划开始"><DatePicker /></Form.Item><Form.Item name={[item.name, "task", "due_date"]} label="计划截止"><DatePicker /></Form.Item><Form.Item name={[item.name, "task", "planned_duration_days"]} label="计划工作日"><InputNumber min={1} max={10000} precision={0} /></Form.Item></Space>
          <Form.Item name={[item.name, "task", "deliverable"]} label="交付物"><Input /></Form.Item><Form.Item name={[item.name, "task", "acceptance_criteria"]} label="验收条件"><Input /></Form.Item>
          <Button onClick={() => remove(item.name)}>移除新增任务</Button>
        </AppCard>)}<Button onClick={() => add({ client_id: Math.min(0, ...(newTasks ?? []).map(task => task.client_id)) - 1, task: {} })}>添加新任务</Button></>}</Form.List>
        <h4>候选完整依赖图</h4>
        <Form.List name="links">{(items, { add, remove }) => <>{items.map(item => <Space key={item.key} wrap>
          <Form.Item name={[item.name, "source_id"]} label="前置" rules={[{ required: true }]}><Select style={{ width: 210 }} options={taskChoices} /></Form.Item><Form.Item name={[item.name, "target_id"]} label="后续" rules={[{ required: true }]}><Select style={{ width: 210 }} options={taskChoices} /></Form.Item><Form.Item name={[item.name, "link_type"]} label="类型" rules={[{ required: true }]}><Select style={{ width: 150 }} options={Object.entries(linkLabels).map(([value, label]) => ({ value, label }))} /></Form.Item><Form.Item name={[item.name, "lag_days"]} label="等待工作日"><InputNumber min={0} max={10000} precision={0} /></Form.Item><Button onClick={() => remove(item.name)}>移除依赖</Button>
        </Space>)}<Button onClick={() => add({ link_type: "FINISH_TO_START", lag_days: 0 })}>添加依赖</Button></>}</Form.List>
        <Form.Item name="override_target" valuePropName="checked"><Checkbox>模拟项目目标变更</Checkbox></Form.Item>
        {targetOverride && <Form.Item name="target_date" label="候选目标（留空移除目标约束）"><DatePicker /></Form.Item>}
        <p>原方案的路线选择会保留。此处仅保存草案；新版本必须重新验证和确认。</p>
      </Form>
    </Modal>
  </AppCard>;
}
