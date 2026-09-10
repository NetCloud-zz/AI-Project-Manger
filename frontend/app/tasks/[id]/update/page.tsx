"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { App, Button, Checkbox, Input } from "antd";
import { SendOutlined } from "@ant-design/icons";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppCard } from "@/components/common/AppCard";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import { ApiError } from "@/lib/http";
import { fetchTask } from "@/services/tasks";
import { submitProgress } from "@/services/progress";
import type { Task } from "@/types/task";

function taskLoadError(error: unknown): { title: string; description: string; retryable: boolean } {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return {
        title: "无权更新此任务",
        description: "你没有权限提交该任务的进展。如需操作请联系项目负责人。",
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
    description: "无法获取任务信息，请稍后重试。",
    retryable: true,
  };
}

function TaskUpdateInner() {
  const params = useParams<{ id: string }>();
  const taskId = Number(params.id);
  const router = useRouter();
  const { message } = App.useApp();
  const { user } = useAuth();
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ReturnType<typeof taskLoadError> | null>(null);
  const [content, setContent] = useState("");
  const [markCompleted, setMarkCompleted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchTask(taskId)
      .then((data) => {
        if (!cancelled) {
          setTask(data);
          setLoadError(null);
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
  }, [taskId, reloadKey]);

  const retry = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    setReloadKey((value) => value + 1);
  }, []);

  const canSubmit = Boolean(
    user &&
      task &&
      (user.role === "ADMIN" || task.owner_id === user.id || user.role === "PROJECT_OWNER"),
  );

  const onSubmit = async () => {
    if (!content.trim()) {
      message.warning("请填写今日进展");
      return;
    }
    setSubmitting(true);
    try {
      await submitProgress(taskId, {
        content: content.trim(),
        mark_completed: markCompleted,
      });
      message.success("✓ 进展已保存，等待 AI 分析");
      router.push(`/tasks/${taskId}`);
    } catch {
      message.error("提交失败，请检查内容后重试");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <PageContainer width="form">
        <LoadingState tip="加载任务…" />
      </PageContainer>
    );
  }

  if (loadError || !task) {
    const info = loadError ?? {
      title: "加载失败",
      description: "无法获取任务信息，请稍后重试。",
      retryable: true,
    };
    return (
      <PageContainer width="form">
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

  if (!canSubmit) {
    return (
      <PageContainer width="form">
        <PageHeader title="无权限" backHref={`/tasks/${taskId}`} />
        <AppCard>
          <p className="meta-line">你没有权限更新此任务进展。</p>
        </AppCard>
      </PageContainer>
    );
  }

  return (
    <PageContainer width="form">
      <PageHeader
        title="更新进展"
        subtitle={`${task.project?.project_name ?? task.project?.project_code} · ${task.task_name}`}
        backHref={`/tasks/${taskId}`}
      />

      <AppCard stack="sm">
        <div className="meta-line">截止 {task.due_date ?? "未定"} · 用一句话描述今日进展</div>
        <Input.TextArea
          className="progress-textarea"
          rows={6}
          placeholder="例如：联调已完成，阻塞项已关闭，预计周五提测。"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          maxLength={5000}
          showCount
          autoFocus
        />
        {/* Wrapper div so the card's stack spacing applies; antd's own
            checkbox styles outrank a bare class selector. */}
        <div>
          <Checkbox
            checked={markCompleted}
            onChange={(event) => setMarkCompleted(event.target.checked)}
          >
            同时标记任务为已完成
          </Checkbox>
        </div>
      </AppCard>

      <Button
        type="primary"
        block
        size="large"
        icon={<SendOutlined />}
        loading={submitting}
        onClick={() => void onSubmit()}
      >
        提交进展
      </Button>
    </PageContainer>
  );
}

export default function TaskUpdatePage() {
  return (
    <RequireAuth>
      <TaskUpdateInner />
    </RequireAuth>
  );
}
