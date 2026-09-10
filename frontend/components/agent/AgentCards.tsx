"use client";

import { Space, Tag } from "antd";
import { CommandPlanCard } from "@/components/agent/CommandPlanCard";

import { AppCard } from "@/components/common/AppCard";
import { AdviceListCard } from "@/components/agent/AdviceListCard";
import { ChangeProposalCard } from "@/components/agent/ChangeProposalCard";
import { NotificationStatusCard } from "@/components/agent/NotificationStatusCard";
import { PlanDraftCard } from "@/components/agent/PlanDraftCard";
import { RiskEventsCard } from "@/components/agent/RiskEventsCard";
import type { AgentCard } from "@/types/agent";

function cardKey(card: AgentCard): string {
  switch (card.type) {
    case "execution_plan":
      return `execution_plan:${card.request_id}`;
    case "plan_draft":
      return `plan_draft:${card.draft_id}`;
    case "change_proposal":
      return `change_proposal:${card.proposal_id}`;
    case "schedule_preview":
      return `schedule_preview:${card.project_id}`;
    case "notification_status":
      return `notification_status:${card.proposal_id ?? card.recipient_id ?? ""}`;
    case "risk_events":
      return `risk_events:${card.project_id}`;
    case "advice":
      return `advice:${card.issue_id}`;
  }
}

function renderCard(card: AgentCard) {
  switch (card.type) {
    case "execution_plan":
      return <CommandPlanCard initial={card} />;
    case "plan_draft":
      return <PlanDraftCard draftId={card.draft_id} />;
    case "change_proposal":
      return <ChangeProposalCard projectId={card.project_id} proposalId={card.proposal_id} />;
    case "notification_status":
      return (
        <NotificationStatusCard projectId={card.project_id} proposalId={card.proposal_id} />
      );
    case "risk_events":
      return <RiskEventsCard projectId={card.project_id} />;
    case "advice":
      return <AdviceListCard issueId={card.issue_id} />;
    case "schedule_preview":
      return (
        <AppCard plain title="排期模拟结果">
          <Space wrap>
            <Tag color={card.feasible ? "green" : "red"}>
              {card.feasible ? "方案可行" : "存在冲突"}
            </Tag>
            <span className="meta-line">涉及 {card.changed_tasks} 项任务</span>
          </Space>
          <p className="meta-line">这是只读模拟，计划没有改变。</p>
        </AppCard>
      );
  }
}

/** Actionable follow-ups the assistant attached to a reply. */
export function AgentCards({ cards }: { cards: AgentCard[] | null | undefined }) {
  if (!cards?.length) return null;
  const latest = [...new Map(cards.map((card) => [cardKey(card), card])).values()];
  return (
    <div className="agent-bubble__cards stack-sm">
      {latest.map((card) => (
        <div key={cardKey(card)}>{renderCard(card)}</div>
      ))}
    </div>
  );
}
