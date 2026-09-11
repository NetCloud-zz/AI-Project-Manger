"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { App, Button, Form, Input, Modal, Select } from "antd";
import { DeleteOutlined, EditOutlined } from "@ant-design/icons";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { TaskBranchesPanel } from "@/components/project/TaskBranchesPanel";
import { TASK_STATUS_OPTIONS, TaskStatusTag } from "@/components/project/StatusTags";
import { useAuth } from "@/components/providers/AuthProvider";
import { ProgressHistory } from "@/components/task/ProgressHistory";
import { ApiError } from "@/lib/http";
import { fetchProject } from "@/services/projects";
import { deleteTask, fetchTask, updateTask } from "@/services/tasks";
import { fetchTaskProgress } from "@/services/progress";
import type { Task, TaskStatus } from "@/types/task";
import type { ProgressUpdate } from "@/types/progress";

function taskLoadError(error: unknown): { title: string; description: string; retryable: boolean } {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return {
        title: "无权查看此任务",
        description: "你不是该任务的负责人或项目成员，无法查看详情。如需访问请联系项目负责人。",
        retryable: false,
      };
    }
    if (error.status === 404) {
      return {
        title: "任务不存在",
        description: "该任务可能已被删除，或编号不正确。",
        retryable: false,
      };
    }
  }
  return {
    title: "加载失败",
    description: "无法获取任务详情，请稍后重试。",
    retryable: true,
  };
}

function errorDetail(error: unknown): string | undefined {
  if (
    error instanceof ApiError &&
    error.payload &&
    typeof error.payload === "object" &&
    "detail" in error.payload &&
    typeof (error.payload as { detail: unknown }).detail === "string"
  ) {
    return (error.payload as { detail: string }).detail;
  }
  return undefined;
}

function TaskDetailInner() {
  const params = useParams<{ id: string }>();
  const taskId = Number(params.id);
  const router = useRouter();
  const { message } = App.useApp();
  const { user } = useAuth();
  const [task, setTask] = useState<Task | null>(null);
  const [progress, setProgress] = useState<ProgressUpdate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ReturnType<typeof taskLoadError> | null>(null);
  const [saving, setSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [canDelete, setCanDelete] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteForm] = Form.useForm<{ reason: string }>();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchTask(taskId), fetchTaskProgress(taskId)])
      .then(async ([taskData, progressData]) => {
        if (cancelled) return;
        setTask(taskData);
        setProgress(progressData);
        setLoadError(null);
        if (user?.role === "ADMIN") {
          setCanDelete(true);
        } else if (user?.role === "PROJECT_OWNER") {
          try {
            const project = await fetchProject(taskData.project_id);
            const ownerIds = new Set(
              (project.owners?.length
                ? project.owners.map((item) => item.id)
                : [project.owner_id]
              ).filter(Boolean),
            );
            setCanDelete(ownerIds.has(user.id));
          } catch {
            setCanDelete(false);
          }
        } else {
          setCanDelete(false);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(taskLoadError(error));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [taskId, reloadKey, user]);

  const retry = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    setReloadKey((value) => value + 1);
  }, []);

  const canUpdateStatus = Boolean(
    user &&
      task &&
      (user.role === "ADMIN" || task.owner_id === user.id || user.role === "PROJECT_OWNER"),
  );
  const canManageBranches = Boolean(canDelete);

  const onStatusChange = async (status: TaskStatus) => {
    if (!task) return;
    setSaving(true);
    try {
      const updated = await updateTask(task.id, {
        status,
        expected_version: task.version ?? 1,
      });
      setTask(updated);
      message.success("状态已更新");
    } catch {
      message.error("更新失败");
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async (values: { reason: string }) => {
    if (!task) return;
    setSaving(true);
    try {
      await deleteTask(task.id, { reason: values.reason.trim() });
      message.success("任务已删除");
      setDeleteOpen(false);
      router.push(`/projects/${task.project_id}`);
    } catch (error) {
      message.error(errorDetail(error) ?? "删除任务失败");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <PageContainer width="narrow">
        <LoadingState tip="加载任务…" />
      </PageContainer>
    );
  }

  if (loadError || !task) {
    const info = loadError ?? {
      title: "加载失败",
      description: "无法获取任务详情，请稍后重试。",
      retryable: true,
    };
    return (
      <PageContainer width="narrow">
        <ErrorState
          title={info.title}
          description={info.description}
          onRetry={info.retryable ? retry : undefined}
          action={
            <Link href="/my-tasks">
              <Button type="link">返回我的任务</Button>
            </Link>
          }
        />
      </PageContainer>
    );
  }

  const schedule =
    task.start_date && task.due_date
      ? `${task.start_date} → ${task.due_date}`
      : task.start_date
        ? `开始 ${task.start_date}`
        : task.due_date
          ? `截止 ${task.due_date}`
          : "日期未定";
  const title =
    task.branch_label != null && task.branch_label !== ""
      ? `[${task.branch_label}] ${task.task_name}`
      : task.task_name;

  return (
    <PageContainer width="narrow">
      <PageHeader
        title={title}
        subtitle={`${task.project?.project_code ?? "项目"} · ${schedule}`}
        backHref={`/projects/${task.project_id}`}
        backLabel={task.project?.project_code ?? "返回项目"}
        action={
          canDelete ? (
            <Button
              danger
              icon={<DeleteOutlined />}
              onClick={() => {
                deleteForm.setFieldsValue({ reason: "" });
                setDeleteOpen(true);
              }}
            >
              删除任务
            </Button>
          ) : undefined
        }
      />

      <div className="task-detail-layout">
        <div className="task-detail-layout__sidebar">
          <AppCard stack="sm">
            <div className="meta-line">负责人 · {task.owner?.name ?? (task.owner_id == null ? "待定" : task.owner_id)}</div>
            {task.branch_label ? (
              <div className="meta-line">
                分支 · {task.branch_label}
                {task.is_active_branch ? "（当前）" : "（非当前）"}
              </div>
            ) : null}
            <div className="chip-row chip-row--flush">
              <TaskStatusTag status={task.status} />
            </div>
            {typeof task.progress_percent === "number" ? (
              <div className="meta-line">完成度 · {task.progress_percent}%</div>
            ) : null}
            {task.completed_at ? (
              <div className="meta-line">
                完成于 {new Date(task.completed_at).toLocaleString("zh-CN")}
              </div>
            ) : null}
          </AppCard>

          {canUpdateStatus ? (
            <AppCard stack="md">
              <Link href={`/tasks/${task.id}/update`} className="list-link">
                <Button type="primary" block icon={<EditOutlined />}>
                  更新进展
                </Button>
              </Link>
              <div>
                <span className="field-label">更新状态</span>
                <Select
                  className="full-width"
                  value={task.status}
                  loading={saving}
                  options={TASK_STATUS_OPTIONS}
                  onChange={(value) => void onStatusChange(value as TaskStatus)}
                />
              </div>
            </AppCard>
          ) : (
            <AppCard>
              <p className="meta-line">你没有修改此任务的权限。</p>
            </AppCard>
          )}
        </div>

        <div className="task-detail-layout__main">
          <TaskBranchesPanel
            task={task}
            canManage={canManageBranches}
            onChanged={async () => {
              setReloadKey((value) => value + 1);
            }}
          />

          <SectionTitle flush>进展历史</SectionTitle>
          <ProgressHistory
            items={progress}
            taskId={taskId}
            canRetry={Boolean(canUpdateStatus)}
          />
        </div>
      </div>

      <Modal
        title="删除任务"
        open={deleteOpen}
        onCancel={() => setDeleteOpen(false)}
        onOk={() => deleteForm.submit()}
        okText="确认删除"
        okButtonProps={{ danger: true }}
        confirmLoading={saving}
        destroyOnHidden
      >
        <p className="detail-text">
          将永久删除任务「{task.task_name}」及其进展、问题等关联数据。仅项目负责人或管理员可操作，
          删除原因会写入审计日志。
        </p>
        <Form form={deleteForm} layout="vertical" onFinish={confirmDelete}>
          <Form.Item
            label="删除原因"
            name="reason"
            rules={[{ required: true, min: 2, message: "请填写删除原因" }]}
          >
            <Input.TextArea rows={3} maxLength={2000} showCount placeholder="请说明删除原因" />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
}

export default function TaskDetailPage() {
  return (
    <RequireAuth>
      <TaskDetailInner />
    </RequireAuth>
  );
}
