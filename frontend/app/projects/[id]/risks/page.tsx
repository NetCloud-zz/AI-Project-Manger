"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { App, Button, Segmented, Space, Statistic, Tabs } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppCard } from "@/components/common/AppCard";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { AdviceCard } from "@/components/risk/AdviceCard";
import { RiskEventList } from "@/components/risk/RiskEventList";
import { listProjectAdvice, listRiskEvents, refreshRiskEvents } from "@/services/risks";
import { ApiError } from "@/lib/http";
import type { AdviceEffectiveness, AdviceRecord } from "@/types/advice";
import { RISK_TYPE_LABELS, type RiskEvent, type RiskEventStatus, type RiskSummary } from "@/types/risk";

function errorText(error: unknown, fallback: string): string {
  if (
    error instanceof ApiError &&
    typeof error.payload === "object" &&
    error.payload !== null &&
    "detail" in error.payload &&
    typeof error.payload.detail === "string"
  ) {
    return error.payload.detail;
  }
  if (error instanceof ApiError && error.status === 422) {
    return "请求参数格式不正确，请刷新页面后重试";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "没有权限执行此操作";
  }
  return fallback;
}

const EMPTY: RiskSummary = {
  total: 0,
  OVERDUE: 0,
  FORECAST_DELAY: 0,
  ISSUE: 0,
  MISSING_DATA: 0,
};

function SummaryBar({ summary }: { summary: RiskSummary }) {
  return (
    <AppCard plain>
      <Space size="large" wrap>
        <Statistic title="未关闭风险" value={summary.total} />
        {(Object.keys(RISK_TYPE_LABELS) as (keyof typeof RISK_TYPE_LABELS)[]).map((key) => (
          <Statistic key={key} title={RISK_TYPE_LABELS[key]} value={summary[key]} />
        ))}
      </Space>
    </AppCard>
  );
}

function RisksPageInner() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);
  const { message } = App.useApp();

  const [events, setEvents] = useState<RiskEvent[]>([]);
  const [summary, setSummary] = useState<RiskSummary>(EMPTY);
  const [advice, setAdvice] = useState<AdviceRecord[]>([]);
  const [effectiveness, setEffectiveness] = useState<AdviceEffectiveness | null>(null);
  const [status, setStatus] = useState<RiskEventStatus>("OPEN");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    (next: RiskEventStatus) =>
      Promise.all([listRiskEvents(projectId, next), listProjectAdvice(projectId)])
        .then(([risks, advices]) => {
          setEvents(risks.items);
          setSummary(risks.summary);
          setAdvice(advices.items);
          setEffectiveness(advices.effectiveness);
          setFailed(false);
        })
        .catch(() => setFailed(true))
        .finally(() => setLoading(false)),
    [projectId],
  );

  useEffect(() => {
    void load(status);
  }, [load, status]);

  const reload = () => {
    setLoading(true);
    void load(status);
  };

  const rescan = () => {
    setBusy(true);
    refreshRiskEvents(projectId, true)
      .then((result) => {
        setEvents(result.items);
        setSummary(result.summary);
        setStatus("OPEN");
        message.success(
          `重新评估完成：新增 ${result.counts.opened ?? 0}，关闭 ${result.counts.resolved ?? 0}`,
        );
      })
      .catch((error: unknown) =>
        message.error(errorText(error, "重新评估失败，可能是没有权限或计划数据有冲突")),
      )
      .finally(() => setBusy(false));
  };

  const onRiskChanged = (next: RiskEvent) =>
    setEvents((prev) =>
      status === "OPEN" && next.status === "RESOLVED"
        ? prev.filter((item) => item.id !== next.id)
        : prev.map((item) => (item.id === next.id ? next : item)),
    );

  const onAdviceChanged = (next: AdviceRecord) =>
    setAdvice((prev) => prev.map((item) => (item.id === next.id ? next : item)));

  if (failed) return <ErrorState description="无法加载风险与建议" onRetry={reload} />;
  if (loading) return <LoadingState tip="加载风险记录…" />;

  return (
    <PageContainer>
      <PageHeader
        title="风险与建议"
        subtitle="每条记录都带有原因、依据和首次发现时间；预测不等于事实，缺数据不等于没风险。"
        action={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={reload}>
              刷新
            </Button>
            <Button type="primary" loading={busy} onClick={rescan}>
              重新评估
            </Button>
          </Space>
        }
      />
      <SummaryBar summary={summary} />

      <Tabs
        items={[
          {
            key: "risks",
            label: `风险记录（${events.length}）`,
            children: (
              <div className="stack-sm">
                <Segmented
                  value={status}
                  onChange={(value) => {
                    setLoading(true);
                    setStatus(value as RiskEventStatus);
                  }}
                  options={[
                    { value: "OPEN", label: "未关闭" },
                    { value: "RESOLVED", label: "已关闭" },
                  ]}
                />
                {events.length === 0 ? (
                  <EmptyState
                    title={status === "OPEN" ? "当前没有未关闭的风险记录" : "没有已关闭的记录"}
                    description={
                      status === "OPEN"
                        ? "这表示检测器没有发现符合条件的情况，不代表项目一定没有问题。"
                        : "关闭的风险会保留依据，便于回溯。"
                    }
                  />
                ) : (
                  <RiskEventList events={events} canResolve onChanged={onRiskChanged} />
                )}
              </div>
            ),
          },
          {
            key: "advice",
            label: `问题建议（${advice.length}）`,
            children: (
              <div className="stack-sm">
                {effectiveness ? (
                  <AppCard plain>
                    <Space size="large" wrap>
                      <Statistic title="建议总数" value={effectiveness.total} />
                      <Statistic title="待处置" value={effectiveness.pending} />
                      <Statistic title="已采纳" value={effectiveness.adopted} />
                      <Statistic title="已评价" value={effectiveness.evaluated} />
                      <Statistic title="评价为有效" value={effectiveness.effective} />
                      <Statistic title="问题已解决" value={effectiveness.issues_resolved} />
                    </Space>
                  </AppCard>
                ) : null}
                {advice.length === 0 ? (
                  <EmptyState
                    title="还没有建议记录"
                    description="在问题详情里请求 AI 建议，生成的版本会连同依据出现在这里。"
                  />
                ) : (
                  advice.map((record) => (
                    <AdviceCard key={record.id} record={record} onChanged={onAdviceChanged} />
                  ))
                )}
              </div>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}

export default function ProjectRisksPage() {
  return (
    <RequireAuth>
      <RisksPageInner />
    </RequireAuth>
  );
}
