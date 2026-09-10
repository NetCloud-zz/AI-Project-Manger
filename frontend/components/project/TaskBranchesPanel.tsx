"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { App, Button, DatePicker, Form, Input, Modal, Switch } from "antd";
import { BranchesOutlined, PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { EmptyState } from "@/components/feedback/EmptyState";
import { TaskStatusTag } from "@/components/project/StatusTags";
import {
  activateTaskBranch,
  createTaskBranch,
  fetchTaskBranches,
} from "@/services/tasks";
import type { Task } from "@/types/task";

type Props = {
  task: Task;
  canManage: boolean;
  onChanged: () => void | Promise<void>;
};

export function TaskBranchesPanel({ task, canManage, onChanged }: Props) {
  const { message } = App.useApp();
  const [branches, setBranches] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activatingId, setActivatingId] = useState<number | null>(null);
  const [form] = Form.useForm<{
    task_name: string;
    branch_label: string;
    due_date?: dayjs.Dayjs;
    activate: boolean;
    reason: string;
  }>();

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setBranches(await fetchTaskBranches(task.id));
    } catch {
      message.error("加载任务分支失败");
    } finally {
      setLoading(false);
    }
  }, [message, task.id]);

  useEffect(() => {
    if (task.branch_option_id != null) return;
    let alive = true;
    fetchTaskBranches(task.id)
      .then(items => { if (alive) setBranches(items); })
      .catch(() => { if (alive) message.error("加载任务分支失败"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [task.id, task.branch_option_id, message]);

  const createBranch = async (values: {
    task_name: string;
    branch_label: string;
    due_date?: dayjs.Dayjs;
    activate: boolean;
    reason: string;
  }) => {
    setSubmitting(true);
    try {
      await createTaskBranch(task.id, {
        task_name: values.task_name,
        branch_label: values.branch_label,
        due_date: values.due_date?.format("YYYY-MM-DD") ?? null,
        activate: values.activate,
        reason: values.reason,
      });
      message.success(values.activate ? "已创建并切换到新分支" : "分支已创建");
      setFormOpen(false);
      form.resetFields();
      await reload();
      await onChanged();
    } catch {
      message.error("创建分支失败");
    } finally {
      setSubmitting(false);
    }
  };

  const activate = async (branch: Task) => {
    const reason = window.prompt(`切换到「${branch.branch_label ?? branch.task_name}」的原因？`);
    if (!reason || reason.trim().length < 2) {
      message.warning("请填写切换原因");
      return;
    }
    setActivatingId(branch.id);
    try {
      await activateTaskBranch(branch.id, { reason: reason.trim() });
      message.success("已切换当前分支");
      await reload();
      await onChanged();
    } catch {
      message.error("切换分支失败");
    } finally {
      setActivatingId(null);
    }
  };

  if (task.branch_option_id != null) {
    return <AppCard><p>此任务属于项目替代路线组，请在计划资料中查看和切换完整路线。</p>
      <Link href={`/projects/${task.project_id}/planning`}>查看项目路线</Link></AppCard>;
  }

  const hasBranches = branches.some((item) => item.branch_root_id != null) || branches.length > 1;

  return (
    <div>
      <SectionTitle
        flush
        extra={
          canManage ? (
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => {
                form.setFieldsValue({
                  task_name: `${task.task_name}（备用）`,
                  branch_label: "备用路线",
                  activate: true,
                  reason: "",
                });
                setFormOpen(true);
              }}
            >
              新增分支
            </Button>
          ) : undefined
        }
      >
        <BranchesOutlined /> 任务分支
      </SectionTitle>

      {loading ? (
        <AppCard>
          <p className="meta-line">加载中…</p>
        </AppCard>
      ) : !hasBranches ? (
        <EmptyState
          title="暂无分支"
          description="当主路线不可行需要换方案时，可从这里创建备用分支并切换。"
        />
      ) : (
        <div className="card-grid">
          {branches.map((branch) => (
            <AppCard key={branch.id} as="article" stack="sm">
              <div className="entity-card__head">
                <Link href={`/tasks/${branch.id}`} className="entity-card__name list-link">
                  {branch.branch_label ? `[${branch.branch_label}] ` : ""}
                  {branch.task_name}
                </Link>
                {branch.is_active_branch ? (
                  <span className="gantt-risk-chip" style={{ background: "#20A472", color: "#fff" }}>
                    当前
                  </span>
                ) : null}
              </div>
              <div className="chip-row chip-row--flush">
                <TaskStatusTag status={branch.status} />
              </div>
              <p className="meta-line">
                负责人：{branch.owner?.name ?? branch.owner_id}
                {branch.due_date ? ` · 截止 ${branch.due_date}` : ""}
              </p>
              {canManage && !branch.is_active_branch ? (
                <Button
                  size="small"
                  loading={activatingId === branch.id}
                  onClick={() => void activate(branch)}
                >
                  切换为当前分支
                </Button>
              ) : null}
            </AppCard>
          ))}
        </div>
      )}

      <Modal
        title="新增任务分支"
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={createBranch} initialValues={{ activate: true }}>
          <Form.Item label="分支名称" name="branch_label" rules={[{ required: true, max: 80 }]}>
            <Input placeholder="例如：备用方案 / 路线 B" />
          </Form.Item>
          <Form.Item label="任务标题" name="task_name" rules={[{ required: true, max: 300 }]}>
            <Input />
          </Form.Item>
          <Form.Item label="截止日期" name="due_date">
            <DatePicker className="full-width" />
          </Form.Item>
          <Form.Item label="创建后立即切换" name="activate" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            label="原因说明"
            name="reason"
            rules={[{ required: true, min: 2, message: "请说明为何新增/切换分支" }]}
          >
            <Input.TextArea rows={3} placeholder="例如：原方案工期或成本不可接受，切换备用路线" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
