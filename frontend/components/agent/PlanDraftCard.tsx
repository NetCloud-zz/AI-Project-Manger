"use client";

import { useCallback, useEffect, useState } from "react";
import { App, Button, Modal, Space, Tag } from "antd";
import { useRouter } from "next/navigation";

import { AppCard } from "@/components/common/AppCard";
import { ApiError } from "@/lib/http";
import {
  discardPlanDraft,
  getPlanDraft,
  publishPlanDraft,
  reviewPlanDraft,
} from "@/services/plan-drafts";
import { PLAN_DRAFT_STATUS_LABELS, type PlanDraft } from "@/types/plan-draft";

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "default",
  REVIEWED: "blue",
  PUBLISHED: "green",
  DISCARDED: "default",
  FAILED: "red",
};

function errorText(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.payload === "object" &&
    error.payload !== null &&
    "detail" in error.payload &&
    typeof error.payload.detail === "string"
  ) {
    return error.payload.detail;
  }
  return "操作未确认，请刷新草案后重试";
}

/** Draft summary with the actions the assistant is not allowed to take on its own. */
export function PlanDraftCard({ draftId }: { draftId: string }) {
  const { message, modal } = App.useApp();
  const router = useRouter();
  const [draft, setDraft] = useState<PlanDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);

  const load = useCallback(
    () =>
      getPlanDraft(draftId)
        .then((row) => {
          setDraft(row);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [draftId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (run: () => Promise<PlanDraft>, done: (next: PlanDraft) => void) => {
    setBusy(true);
    try {
      const next = await run();
      setDraft(next);
      done(next);
    } catch (error) {
      message.error(errorText(error));
      void load();
    } finally {
      setBusy(false);
    }
  };

  const onReview = () =>
    act(
      () => reviewPlanDraft(draftId, draft!.revision),
      (next) => {
        const blocking = next.review?.blocking ?? [];
        if (blocking.length) message.warning(`还有 ${blocking.length} 项必须补齐才能发布`);
        else message.success("校验通过，可以发布");
      },
    );

  const onPublish = () => {
    if (!draft?.digest) return;
    modal.confirm({
      title: "发布计划？",
      content: "将以你的账号创建项目、任务、依赖和里程碑，并保存为基线版本。此操作不可撤销。",
      okText: "确认发布",
      cancelText: "再看看",
      onOk: () =>
        act(
          () =>
            publishPlanDraft(draftId, {
              expected_revision: draft.revision,
              digest: draft.digest!,
              idempotency_key: `publish:${draftId}:${draft.revision}`,
            }),
          (next) => {
            if (next.status === "PUBLISHED" && next.project_id) {
              message.success("项目已创建");
              router.push(`/projects/${next.project_id}`);
            } else {
              message.warning(next.failure_reason ?? "发布未完成，请查看草案状态");
            }
          },
        ),
    });
  };

  const onDiscard = () =>
    modal.confirm({
      title: "废弃这份草案？",
      okText: "废弃",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: () =>
        act(
          () => discardPlanDraft(draftId, draft!.revision),
          () => message.success("草案已废弃"),
        ),
    });

  if (failed) {
    return (
      <AppCard plain>
        <Space>
          <span>无法读取计划草案</span>
          <Button size="small" onClick={() => void load()}>
            重试
          </Button>
        </Space>
      </AppCard>
    );
  }
  if (!draft) return null;

  const review = draft.review;
  const blocking = review?.blocking ?? [];
  const warnings = review?.warnings ?? [];
  const content = draft.content;
  const editable = !["PUBLISHED", "DISCARDED"].includes(draft.status);

  return (
    <AppCard plain stack="sm" title={`计划草案 · ${draft.title}`}>
      <Space wrap>
        <Tag color={STATUS_COLORS[draft.status]}>{PLAN_DRAFT_STATUS_LABELS[draft.status]}</Tag>
        <span className="meta-line">第 {draft.revision} 版</span>
        <span className="meta-line">
          {content.project.project_code} · 任务 {content.tasks.length} · 依赖{" "}
          {content.links.length} · 里程碑 {content.milestones.length}
        </span>
      </Space>

      {draft.status === "PUBLISHED" && draft.project_id ? (
        <p>
          已创建项目 {content.project.project_name}。
          <Button type="link" size="small" onClick={() => router.push(`/projects/${draft.project_id}`)}>
            打开项目
          </Button>
        </p>
      ) : null}
      {draft.failure_reason ? (
        <p className="meta-line meta-line--danger">{draft.failure_reason}</p>
      ) : null}

      {blocking.length ? (
        <div>
          <strong>必须补齐（{blocking.length}）</strong>
          {blocking.map((item) => (
            <p key={item}>· {item}</p>
          ))}
        </div>
      ) : null}
      {warnings.length ? (
        <div>
          <strong>建议确认（{warnings.length}）</strong>
          {warnings.map((item) => (
            <p key={item}>· {item}</p>
          ))}
        </div>
      ) : null}
      {review == null ? <p>尚未校验，校验通过后才能发布。</p> : null}

      <Space wrap>
        <Button size="small" onClick={() => setDetailOpen(true)}>
          查看完整草案
        </Button>
        {editable ? (
          <Button size="small" loading={busy} onClick={() => void onReview()}>
            重新校验
          </Button>
        ) : null}
        {draft.status === "REVIEWED" && draft.digest ? (
          <Button type="primary" size="small" loading={busy} onClick={onPublish}>
            发布并创建项目
          </Button>
        ) : null}
        {editable ? (
          <Button size="small" danger disabled={busy} onClick={onDiscard}>
            废弃
          </Button>
        ) : null}
      </Space>

      <Modal
        open={detailOpen}
        title={`计划草案 · ${draft.title}`}
        footer={null}
        width={900}
        onCancel={() => setDetailOpen(false)}
      >
        <p>
          {content.project.project_name}（{content.project.project_code}）
          {content.project.start_date ?? "未定开始"} ~ {content.project.target_date ?? "未定目标"}
        </p>
        {content.project.goal ? <p>目标：{content.project.goal}</p> : null}
        <h4>任务</h4>
        {content.tasks.map((task) => (
          <p key={task.client_id}>
            {task.task_name} · {task.start_date ?? "未定"} ~ {task.due_date ?? "未定"} ·{" "}
            {task.planned_duration_days ?? "?"} 工作日
            {task.estimate_basis ? ` · 估算依据：${task.estimate_basis}` : ""}
          </p>
        ))}
        {content.milestones.length ? <h4>里程碑</h4> : null}
        {content.milestones.map((milestone) => (
          <p key={milestone.client_id}>
            {milestone.name} · {milestone.target_date ?? "未定"}
          </p>
        ))}
        {content.links.length ? <h4>依赖</h4> : null}
        {content.links.map((link) => (
          <p key={`${link.source_client_id}-${link.target_client_id}`}>
            {content.tasks.find((task) => task.client_id === link.source_client_id)?.task_name} →{" "}
            {content.tasks.find((task) => task.client_id === link.target_client_id)?.task_name} ·
            等待 {link.lag_days} 工作日
          </p>
        ))}
        {content.assumptions.length ? <h4>假设</h4> : null}
        {content.assumptions.map((item) => (
          <p key={item}>· {item}</p>
        ))}
        {content.open_questions.length ? <h4>待确认问题</h4> : null}
        {content.open_questions.map((item) => (
          <p key={item}>· {item}</p>
        ))}
      </Modal>
    </AppCard>
  );
}
