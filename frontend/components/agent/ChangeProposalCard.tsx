"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Space, Tag } from "antd";
import { useRouter } from "next/navigation";

import { AppCard } from "@/components/common/AppCard";
import { getProposal } from "@/services/change-proposals";
import type { ChangeProposal } from "@/types/change-proposal";

const LABELS: Record<ChangeProposal["status"], string> = {
  DRAFT: "草案",
  VALIDATED: "已验证，待你核对确认",
  CONFIRMED: "已确认，待执行",
  APPLIED: "已执行",
  REJECTED: "已拒绝",
  EXPIRED: "已过期",
  FAILED: "执行失败",
};

const COLORS: Record<ChangeProposal["status"], string> = {
  DRAFT: "default",
  VALIDATED: "blue",
  CONFIRMED: "gold",
  APPLIED: "green",
  REJECTED: "default",
  EXPIRED: "default",
  FAILED: "red",
};

/**
 * Summary only. Confirming and applying stay on the planning page where the
 * full diff is shown, because that is where the user actually authorises them.
 */
export function ChangeProposalCard({
  projectId,
  proposalId,
}: {
  projectId: number;
  proposalId: string;
}) {
  const router = useRouter();
  const [proposal, setProposal] = useState<ChangeProposal | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    () =>
      getProposal(projectId, proposalId)
        .then((row) => {
          setProposal(row);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [projectId, proposalId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (failed) {
    return (
      <AppCard plain>
        <Space>
          <span>无法读取变更方案</span>
          <Button size="small" onClick={() => void load()}>
            重试
          </Button>
        </Space>
      </AppCard>
    );
  }
  if (!proposal) return null;

  const conflicts = proposal.preview?.candidate.conflicts ?? [];
  const changedTasks = proposal.diff?.tasks.length ?? 0;
  const recipients = proposal.diff?.notifications.length ?? 0;

  return (
    <AppCard plain stack="sm" title="变更方案">
      <Space wrap>
        <Tag color={COLORS[proposal.status]}>{LABELS[proposal.status]}</Tag>
        <span className="meta-line">第 {proposal.revision} 版</span>
        <span className="meta-line">
          影响任务 {changedTasks} 项 · 通知对象 {recipients} 人
        </span>
      </Space>
      <p>{proposal.reason}</p>
      <p className="meta-line">
        候选预测完成：{proposal.preview?.candidate.project_finish_date ?? "尚未验证"}
      </p>
      {conflicts.map((conflict) => (
        <p key={conflict.message} className="meta-line meta-line--danger">
          {conflict.message}　{conflict.suggestion}
        </p>
      ))}
      {proposal.failure_reason ? (
        <p className="meta-line meta-line--danger">{proposal.failure_reason}</p>
      ) : null}
      <Space wrap>
        <Button
          type={proposal.status === "VALIDATED" ? "primary" : "default"}
          size="small"
          onClick={() => router.push(`/projects/${projectId}/planning?proposal=${proposal.id}`)}
        >
          {proposal.status === "APPLIED" ? "查看已执行方案" : "核对完整差异并处理"}
        </Button>
        <Button size="small" onClick={() => void load()}>
          刷新状态
        </Button>
      </Space>
      {proposal.status !== "APPLIED" ? (
        <p className="meta-line">计划尚未改变，需要你在方案页核对后确认执行。</p>
      ) : null}
    </AppCard>
  );
}
