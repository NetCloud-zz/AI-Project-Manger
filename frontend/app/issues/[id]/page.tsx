"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { App, Button, Select } from "antd";
import { ReloadOutlined, RobotOutlined } from "@ant-design/icons";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  ISSUE_STATUS_OPTIONS,
  ActionItemStatusTag,
  IssueSeverityTag,
  IssueStatusTag,
} from "@/components/project/StatusTags";
import { useAuth } from "@/components/providers/AuthProvider";
import { fetchProjectActionItems } from "@/services/action_items";
import {
  fetchIssue,
  parseAiSuggestedSolution,
  requestIssueAdvice,
  updateIssue,
} from "@/services/issues";
import { fetchAIRun } from "@/services/ai_runs";
import { AdviceCard } from "@/components/risk/AdviceCard";
import { listIssueAdvice } from "@/services/risks";
import { ApiError } from "@/lib/http";
import type { ActionItem } from "@/types/action_item";
import type { AdviceRecord } from "@/types/advice";
import type { Issue, IssueStatus } from "@/types/issue";

function AiAdviceBlock({ raw }: { raw: string }) {
  const { isAi, advice } = parseAiSuggestedSolution(raw);
  if (!isAi || !advice) {
    return <p className="detail-text">{raw}</p>;
  }

  const renderList = (label: string, items: unknown) => {
    if (!Array.isArray(items) || items.length === 0) return null;
    return (
      <div>
        <span className="field-label">{label}</span>
        <ul className="detail-list">
          {items.map((item, idx) => (
            <li key={idx}>{String(item)}</li>
          ))}
        </ul>
      </div>
    );
  };

  return (
    <div className="stack-sm">
      {advice.problem_summary ? (
        <div>
          <span className="field-label">问题摘要</span>
          <p className="detail-text">{String(advice.problem_summary)}</p>
        </div>
      ) : null}
      {renderList("可能原因", advice.possible_causes)}
      {renderList("建议核查", advice.checks)}
      {renderList("建议下一步", advice.recommended_next_actions)}
      {renderList("建议参与方", advice.suggested_participants)}
      {typeof advice.escalation_recommended === "boolean" ? (
        <p className="detail-text">建议升级：{advice.escalation_recommended ? "是" : "否"}</p>
      ) : null}
    </div>
  );
}

function IssueDetailInner() {
  const params = useParams<{ id: string }>();
  const issueId = Number(params.id);
  const { message } = App.useApp();
  const { user } = useAuth();
  const [issue, setIssue] = useState<Issue | null>(null);
  const [followUps, setFollowUps] = useState<ActionItem[]>([]);
  const [advice, setAdvice] = useState<AdviceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [advising, setAdvising] = useState(false);
  const [adviceStatus, setAdviceStatus] = useState<string | null>(null);
  const [savingStatus, setSavingStatus] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  /*
   * Only show the loading state when there is nothing to display yet.
   * A refresh with content on screen updates in place instead of blanking
   * the page and losing the scroll position.
   */
  const reload = useCallback(() => {
    setLoading((prev) => prev || issue === null);
    setFailed(false);
    setReloadKey((value) => value + 1);
  }, [issue]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await fetchIssue(issueId);
        if (cancelled) return;
        setIssue(data);
        const items = await fetchProjectActionItems(data.project_id);
        if (!cancelled) setFollowUps(items.filter((item) => item.issue_id === issueId));
        const records = await listIssueAdvice(issueId);
        if (!cancelled) setAdvice(records.items);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [issueId, reloadKey]);

  const onChangeStatus = async (next: IssueStatus) => {
    setSavingStatus(true);
    try {
      const updated = await updateIssue(issueId, { status: next });
      setIssue(updated);
      message.success("问题状态已更新");
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        message.error("只有管理员或项目负责人可以修改问题状态");
      } else {
        message.error("更新问题状态失败");
      }
    } finally {
      setSavingStatus(false);
    }
  };

  const onRequestAdvice = async () => {
    setAdvising(true);
    setAdviceStatus("QUEUED");
    try {
      const res = await requestIssueAdvice(issueId);
      message.success("AI 建议生成中…");
      if (res.ai_run_id) {
        const runId = res.ai_run_id;
        const started = Date.now();
        while (Date.now() - started < 90_000) {
          await new Promise((r) => setTimeout(r, 2500));
          const run = await fetchAIRun(runId);
          setAdviceStatus(run.status);
          if (
            run.status === "SUCCEEDED" ||
            run.status === "FAILED" ||
            run.status === "DISABLED"
          ) {
            if (run.status === "SUCCEEDED") {
              message.success("AI 建议已生成");
              reload();
            } else if (run.status === "DISABLED") {
              message.warning(run.user_message || "LLM 未启用");
            } else {
              message.error(run.user_message || "AI 建议生成失败");
            }
            break;
          }
        }
      }
    } catch {
      message.error("请求 AI 建议失败");
      setAdviceStatus("FAILED");
    } finally {
      setAdvising(false);
    }
  };

  if (loading) {
    return (
      <PageContainer width="narrow">
        <LoadingState tip="加载 Issue…" />
      </PageContainer>
    );
  }

  if (failed || !issue) {
    return (
      <PageContainer width="narrow">
        <ErrorState description="无法获取 Issue 详情，请稍后重试。" onRetry={reload} />
      </PageContainer>
    );
  }

  const showAiLabel =
    issue.suggested_solution_is_ai ||
    parseAiSuggestedSolution(issue.suggested_solution).isAi;
  // The server is the authority; hide the control only for read-only roles.
  const canEditStatus = Boolean(user && user.role !== "EXECUTIVE");

  return (
    <PageContainer width="narrow">
      <PageHeader
        backHref={`/projects/${issue.project_id}`}
        backLabel="返回项目"
        title={issue.title}
        action={
          <Button icon={<ReloadOutlined />} onClick={reload}>
            刷新
          </Button>
        }
      />

      <div className="chip-row chip-row--flush">
        <IssueSeverityTag severity={issue.severity} />
        <IssueStatusTag status={issue.status} />
        {canEditStatus ? (
          <Select
            size="small"
            value={issue.status}
            loading={savingStatus}
            options={ISSUE_STATUS_OPTIONS}
            onChange={(value) => void onChangeStatus(value as IssueStatus)}
            style={{ minWidth: 110 }}
          />
        ) : null}
      </div>

      <SectionTitle>描述</SectionTitle>
      <AppCard as="article">
        <p className="detail-text">{issue.description}</p>
        <p className="meta-line meta-line--spaced">
          {issue.task ? `关联任务：${issue.task.task_name}` : "项目级问题（未绑定任务）"}
          {issue.reporter ? ` · 登记人：${issue.reporter.name}` : ""}
        </p>
      </AppCard>

      <SectionTitle>跟进的行动项</SectionTitle>
      {followUps.length === 0 ? (
        <AppCard>
          <p className="meta-line">
            暂无关联行动项。可在项目页新建行动项并关联本问题，形成「问题 → 行动」闭环。
          </p>
        </AppCard>
      ) : (
        <div className="card-grid">
          {followUps.map((item) => (
            <AppCard key={item.id} as="article" stack="sm">
              <div className="entity-card__name">{item.title}</div>
              <div className="chip-row chip-row--flush">
                <ActionItemStatusTag status={item.status} />
              </div>
              <p className="meta-line">
                {`负责人：${item.owner?.name ?? "未指派"}`}
                {item.due_date ? ` · 截止：${item.due_date}` : ""}
              </p>
            </AppCard>
          ))}
        </div>
      )}

      <SectionTitle
        extra={
          <Button loading={advising} onClick={() => void onRequestAdvice()}>
            请求 AI 建议
          </Button>
        }
      >
        解决建议
      </SectionTitle>

      {adviceStatus === "QUEUED" || adviceStatus === "RUNNING" ? (
        <AppCard>
          <p className="meta-line meta-line--accent">AI 建议生成中…</p>
        </AppCard>
      ) : null}

      {adviceStatus === "FAILED" ? (
        <AppCard>
          <p className="meta-line" style={{ color: "var(--app-color-danger)" }}>
            ⚠ AI 建议生成失败
          </p>
          <Button size="small" onClick={() => void onRequestAdvice()}>
            重新请求
          </Button>
        </AppCard>
      ) : null}

      {advice.length > 0 ? (
        <div className="stack-sm">
          {advice.map((record) => (
            <AdviceCard
              key={record.id}
              record={record}
              onChanged={(next) =>
                setAdvice((prev) => prev.map((item) => (item.id === next.id ? next : item)))
              }
            />
          ))}
        </div>
      ) : !issue.suggested_solution ? (
        <AppCard>
          <p className="meta-line">
            暂无建议。可点击「请求 AI 建议」生成辅助方案（非正式业务决策）。
          </p>
        </AppCard>
      ) : (
        // Advice written before S5, or edited by hand: text only, nothing to adopt.
        <AppCard as="article" stack="sm">
          {showAiLabel ? (
            <div>
              <span className="ai-badge">
                <RobotOutlined /> AI 建议
              </span>
            </div>
          ) : null}
          <AiAdviceBlock raw={issue.suggested_solution} />
        </AppCard>
      )}
    </PageContainer>
  );
}

export default function IssueDetailPage() {
  return (
    <RequireAuth>
      <IssueDetailInner />
    </RequireAuth>
  );
}
