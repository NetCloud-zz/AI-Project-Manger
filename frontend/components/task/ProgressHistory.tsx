"use client";

import { useCallback, useEffect, useState } from "react";
import { App, Button } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import { AppCard } from "@/components/common/AppCard";
import { EmptyState } from "@/components/feedback/EmptyState";
import { fetchLatestAIRun } from "@/services/ai_runs";
import { request } from "@/lib/http";
import type { AIRun } from "@/types/ai_run";
import type { ProgressUpdate } from "@/types/progress";

type Props = {
  items: ProgressUpdate[];
  emptyText?: string;
  taskId?: number;
  canRetry?: boolean;
};

function AiStatusLine({
  item,
  run,
  canRetry,
  onRetry,
  retrying,
}: {
  item: ProgressUpdate;
  run: AIRun | null;
  canRetry?: boolean;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  if (run?.status === "QUEUED") {
    return <p className="meta-line meta-line--accent">已保存，等待 AI 分析…</p>;
  }
  if (run?.status === "RUNNING") {
    return <p className="meta-line meta-line--accent">AI 分析中…</p>;
  }
  if (run?.status === "DISABLED") {
    return <p className="meta-line">LLM 未启用，已跳过 AI 分析</p>;
  }
  if (item.ai_analysis_failed || run?.status === "FAILED") {
    return (
      <div className="stack-sm">
        <p className="meta-line" style={{ color: "var(--app-color-danger)" }}>
          ⚠ AI 分析失败（原始进展已保存）
        </p>
        {canRetry && onRetry ? (
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={retrying}
            onClick={onRetry}
          >
            重新分析
          </Button>
        ) : null}
      </div>
    );
  }
  if (item.summary) {
    return <p className="meta-line meta-line--accent">✓ AI 已完成分析 · {item.summary}</p>;
  }
  if (!item.summary && !item.ai_analysis_failed) {
    return <p className="meta-line">✓ 进展已保存</p>;
  }
  return null;
}

export function ProgressHistory({
  items,
  emptyText = "暂无进展记录",
  taskId,
  canRetry = false,
}: Props) {
  const { message } = App.useApp();
  const [runs, setRuns] = useState<Record<number, AIRun | null>>({});
  const [retryingId, setRetryingId] = useState<number | null>(null);

  const loadRuns = useCallback(async () => {
    const pending = items.filter(
      (item) => !item.summary && !item.ai_analysis_failed,
    );
    const next: Record<number, AIRun | null> = {};
    await Promise.all(
      items.slice(0, 10).map(async (item) => {
        try {
          next[item.id] = await fetchLatestAIRun({
            resourceType: "progress_update",
            resourceId: item.id,
            runType: "PROGRESS_ANALYSIS",
          });
        } catch {
          next[item.id] = null;
        }
      }),
    );
    setRuns(next);
    return pending.some((item) => {
      const run = next[item.id];
      return run?.status === "QUEUED" || run?.status === "RUNNING";
    });
  }, [items]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    void (async () => {
      const needsPoll = await loadRuns();
      if (cancelled || !needsPoll) return;
      timer = setInterval(() => {
        void loadRuns();
      }, 2500);
    })();
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [loadRuns]);

  const onRetry = async (progressId: number) => {
    if (!taskId) return;
    setRetryingId(progressId);
    try {
      await request(`/api/v1/tasks/${taskId}/progress/${progressId}/reanalyze`, {
        method: "POST",
      });
      message.success("已重新排队 AI 分析");
      await loadRuns();
    } catch {
      message.error("重新分析失败");
    } finally {
      setRetryingId(null);
    }
  };

  if (items.length === 0) {
    return <EmptyState title={emptyText} />;
  }

  return (
    <div className="stack-sm">
      {items.map((item) => (
        <AppCard key={item.id} as="article" stack="sm">
          <div className="meta-line">{new Date(item.created_at).toLocaleString("zh-CN")}</div>
          <p className="detail-text">{item.raw_content}</p>
          <AiStatusLine
            item={item}
            run={runs[item.id] ?? null}
            canRetry={canRetry}
            retrying={retryingId === item.id}
            onRetry={() => void onRetry(item.id)}
          />
        </AppCard>
      ))}
    </div>
  );
}
