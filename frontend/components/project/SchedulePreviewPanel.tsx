"use client";

import { useState } from "react";
import { Alert, App, Button, Checkbox, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tag } from "antd";
import type { Dayjs } from "dayjs";
import { AppCard } from "@/components/common/AppCard";
import { ApiError } from "@/lib/http";
import { createProposal, proposalAction } from "@/services/change-proposals";
import { previewSchedule } from "@/services/scheduling";
import type { PlanningContext } from "@/types/planning";
import type { SchedulePreview } from "@/types/scheduling";

type Change = {
  task_id: number;
  planned_duration_days?: number | null;
  remaining_duration_days?: number | null;
  start_date?: Dayjs | null;
  due_date?: Dayjs | null;
};
type Values = {
  as_of?: Dayjs | null;
  mode: "preserve_dates" | "earliest";
  changes?: Change[];
  selections?: Record<string, number | undefined>;
  override_target?: boolean;
  target_date?: Dayjs | null;
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload !== null && "detail" in error.payload) {
    if (typeof error.payload.detail === "string") return error.payload.detail;
    if (Array.isArray(error.payload.detail)) return "输入校验失败，请检查重复任务、日期和工期";
  }
  return "预览失败，请重试";
}

const delta = (value: number | null) => value === null ? "无法比较" : value > 0 ? `延后 ${value} 工作日` : value < 0 ? `提前 ${-value} 工作日` : "不变";

export function SchedulePreviewPanel({ projectId, data, onProposalCreated }: { projectId: number; data: PlanningContext; onProposalCreated?: () => void }) {
  const { message } = App.useApp();
  const [form] = Form.useForm<Values>();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SchedulePreview | null>(null);
  const [lastRequest, setLastRequest] = useState<Record<string, unknown> | null>(null);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<{ key: string; reason: string } | null>(null);
  const overrideTarget = Form.useWatch("override_target", form);

  const calculate = async (values: Values) => {
    setBusy(true);
    setResult(null);
    try {
      const changes = (values.changes ?? []).map(change => ({
        task_id: change.task_id,
        ...(change.planned_duration_days != null ? { planned_duration_days: change.planned_duration_days } : {}),
        ...(change.remaining_duration_days != null ? { remaining_duration_days: change.remaining_duration_days } : {}),
        ...(change.start_date ? { start_date: change.start_date.format("YYYY-MM-DD") } : {}),
        ...(change.due_date ? { due_date: change.due_date.format("YYYY-MM-DD") } : {}),
      }));
      const requestBody = {
        mode: values.mode,
        ...(values.as_of ? { as_of: values.as_of.format("YYYY-MM-DD") } : {}),
        changes,
        selections: Object.entries(values.selections ?? {})
          .filter(([, optionId]) => optionId != null)
          .map(([groupId, optionId]) => ({ group_id: Number(groupId), option_id: optionId })),
        ...(values.override_target ? { project_target_date: values.target_date?.format("YYYY-MM-DD") ?? null } : {}),
      };
      const next = await previewSchedule(projectId, requestBody);
      setLastRequest({ ...requestBody, expected_snapshot_token: next.snapshot_token });
      setResult(next);
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };
  const saveDraft = async () => {
    if (!draft || !lastRequest || draft.reason.trim().length < 2) { message.warning("请填写变更原因"); return; }
    setSaving(true);
    try {
      const created = await createProposal(projectId, { reason: draft.reason.trim(), change: lastRequest, idempotency_key: draft.key });
      if (created.status === "DRAFT") await proposalAction(projectId, created.id, "validate", { expected_revision: created.revision });
      setDraft(null); onProposalCreated?.(); message.success("方案已保存，请到变更方案页核对并确认");
    } catch (error) { onProposalCreated?.(); message.error(errorMessage(error)); } finally { setSaving(false); }
  };
  const taskName = (id: number) => data.tasks.find(task => task.id === id)?.task_name ?? `#${id}`;

  return <div>
    <Alert type="info" title="排期预览不会保存任务日期、切换执行路线或修改项目目标。如需执行，请保存为变更方案，核对完整差异后确认。" />
    <AppCard>
      <Form form={form} layout="vertical" initialValues={{ mode: "preserve_dates" }} onFinish={calculate} onValuesChange={() => setResult(null)} disabled={busy}>
        <Space wrap align="start">
          <Form.Item name="mode" label="计算方式">
            <Select style={{ width: 260 }} options={[
              { value: "preserve_dates", label: "保留当前安排，仅传播必要延期" },
              { value: "earliest", label: "计算最早可行方案（保护固定日期）" },
            ]} />
          </Form.Item>
          <Form.Item name="as_of" label="预测基准日">
            <DatePicker placeholder="留空使用项目时区的今天" style={{ width: 260 }} />
          </Form.Item>
        </Space>
        <p>可直接预览当前计划，也可添加假设变更。工期按整数工作日计，留空表示不修改；已开始任务请调整剩余工期。</p>
        <Form.List name="changes">{(fields, { add, remove }) => <>
          {fields.map(field => <AppCard key={field.key}>
            <Form.Item name={[field.name, "task_id"]} label="变更任务" rules={[{ required: true }]}>
              <Select showSearch optionFilterProp="label" options={data.tasks.filter(task => task.status !== "COMPLETED").map(task => ({ value: task.id, label: `${task.task_name}${task.is_active_branch ? "" : "（备用 / 历史）"}` }))} />
            </Form.Item>
            <Space wrap align="start">
              <Form.Item name={[field.name, "planned_duration_days"]} label="候选计划工期"><InputNumber min={1} max={10000} precision={0} /></Form.Item>
              <Form.Item name={[field.name, "remaining_duration_days"]} label="候选剩余工期"><InputNumber min={0} max={10000} precision={0} /></Form.Item>
              <Form.Item name={[field.name, "start_date"]} label="候选开始下限"><DatePicker /></Form.Item>
              <Form.Item name={[field.name, "due_date"]} label="请求截止（严格约束）"><DatePicker /></Form.Item>
              <Button onClick={() => remove(field.name)}>移除变更</Button>
            </Space>
          </AppCard>)}
          <Button onClick={() => add()}>添加假设变更</Button>
        </>}</Form.List>
        <p className="meta-line">请求截止日期会作为严格约束校验，不会倒推出或压缩工期。需要提前时选择“最早可行方案”。</p>
        {data.branch_groups.map(group => <Form.Item key={group.id} name={["selections", String(group.id)]} label={`候选路线：${group.name}`}>
          <Select allowClear placeholder="留空保留当前路线" options={data.branch_options.filter(option => option.group_id === group.id).map(option => ({ value: option.id, label: `${option.name}${option.is_selected ? "（当前）" : ""}` }))} />
        </Form.Item>)}
        <Form.Item name="override_target" valuePropName="checked"><Checkbox>模拟项目目标日期变更</Checkbox></Form.Item>
        {overrideTarget && <Form.Item name="target_date" label="候选目标日期（留空模拟移除目标约束）"><DatePicker /></Form.Item>}
        <Button type="primary" htmlType="submit" loading={busy}>计算预览</Button>
      </Form>
    </AppCard>
    <Modal open={Boolean(draft)} title="保存待审变更方案" onCancel={() => { if (!saving) setDraft(null); }} onOk={() => void saveDraft()} confirmLoading={saving}>
      <p>保存和验证不会改动当前计划。执行前还需核对完整差异并确认。</p>
      <Input.TextArea value={draft?.reason ?? ""} onChange={event => setDraft(value => value ? { ...value, reason: event.target.value } : value)} placeholder="变更原因" maxLength={2000} />
    </Modal>
    {result && <>
      <AppCard>
        <Alert type={result.candidate.feasible ? "success" : "warning"} title={result.candidate.feasible ? "候选排期满足已录入的约束" : "候选方案不可行或资料不完整"} />
        {data.editable && result.candidate.feasible && <Button type="primary" onClick={() => setDraft({ key: crypto.randomUUID(), reason: "" })}>保存为待审方案</Button>}
        <p>预测基准日：{result.as_of} · 日历版本：{result.calendar_version}</p>
        <p>当前计划预测完成：{result.current.project_finish_date ?? "无法确定"} → 候选预测完成：{result.candidate.project_finish_date ?? "无法确定"}（{delta(result.forecast_delta_workdays)}）</p>
        <p>当前目标：{result.current_target_date ?? "未设置"} · 候选目标：{result.proposed_target_date ?? "未设置"} · 候选目标偏差：{result.candidate.target_variance_calendar_days == null ? "无目标比较" : `${result.candidate.target_variance_calendar_days} 自然日`}</p>
        {result.candidate.conflicts.map((issue, index) => <Alert key={index} type="error" title={issue.message} description={<>{issue.task_ids.map(taskName).join("、")} · {issue.suggestion}</>} />)}
        {result.candidate.warnings.map((issue, index) => <Alert key={index} type="info" title={issue.message} />)}
        {!result.current.feasible && <Alert type="info" title="当前计划也存在冲突或资料缺失；请结合候选结果核对，不把当前预测当作可执行基准。" />}
        <p>关键路径示例：{result.candidate.critical_path.map(taskName).join(" → ") || "暂无"}</p>
        <p className="meta-line">关键路径可能有多条，表格标记全部关键任务。总时差包含已录入固定约束；网络时差仅反映项目完成时间余量。</p>
      </AppCard>
      <AppCard>
        <h3>基准、当前计划与候选日期差异</h3>
        <p className="meta-line">{result.baseline ? `对比基准：版本 ${result.baseline.version}（${result.baseline.kind === "MIGRATION_BASELINE" ? "迁移时基准，不代表原始立项计划" : "首次保存基准"}）` : "尚未保存基准版本，基准日期留空。"}</p>
        <Table rowKey="task_id" dataSource={result.changes} scroll={{ x: 950 }} columns={[
          { title: "任务", dataIndex: "task_name" },
          { title: "基准开始", dataIndex: "baseline_start_date" },
          { title: "基准截止", dataIndex: "baseline_due_date" },
          { title: "当前开始", dataIndex: "current_start_date" },
          { title: "当前截止", dataIndex: "current_due_date" },
          { title: "候选开始", dataIndex: "predicted_start_date" },
          { title: "候选完成", dataIndex: "predicted_finish_date" },
          { title: "截止变化", render: (_, row) => delta(row.finish_delta_workdays) },
        ]} />
      </AppCard>
      <AppCard>
        <h3>候选任务预测与时差</h3>
        <Table rowKey="task_id" dataSource={result.candidate.tasks} scroll={{ x: 1050 }} columns={[
          { title: "任务", dataIndex: "task_name" },
          { title: "实际开始", dataIndex: "actual_start_date" },
          { title: "实际完成", dataIndex: "actual_finish_date" },
          { title: "预测开始", dataIndex: "start_date" },
          { title: "预测完成", dataIndex: "finish_date" },
          { title: "总时差 / 网络时差", render: (_, row) => `${row.total_float_workdays ?? "—"} / ${row.network_float_workdays ?? "—"} 工作日` },
          { title: "关键任务", render: (_, row) => row.critical ? <Tag color="red">关键</Tag> : "—" },
        ]} />
        {result.branch_dispositions.map(row => <p key={row.task_id}>{taskName(row.task_id)}：{row.reason}（仅预览）</p>)}
        <p className="meta-line">排除 {result.excluded_task_ids.length} 个备用或取消任务。预览后若计划有变化，请重新计算。</p>
        {result.notices.map(notice => <p className="meta-line" key={notice}>{notice}</p>)}
      </AppCard>
    </>}
  </div>;
}
