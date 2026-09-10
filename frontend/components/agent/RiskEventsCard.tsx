"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button, Space, Tag } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import { AppCard } from "@/components/common/AppCard";
import { listRiskEvents } from "@/services/risks";
import {
  RISK_LEVEL_COLORS,
  RISK_LEVEL_LABELS,
  RISK_TYPE_LABELS,
  type RiskEvent,
  type RiskSummary,
} from "@/types/risk";

/** Reads the current records rather than trusting what the model just said. */
export function RiskEventsCard({ projectId }: { projectId: number }) {
  const [events, setEvents] = useState<RiskEvent[]>([]);
  const [summary, setSummary] = useState<RiskSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    () =>
      listRiskEvents(projectId, "OPEN")
        .then((result) => {
          setEvents(result.items);
          setSummary(result.summary);
          setFailed(false);
        })
        .catch(() => setFailed(true))
        .finally(() => setLoading(false)),
    [projectId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <AppCard
      plain
      stack="sm"
      title="风险记录"
      extra={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => {
            setLoading(true);
            void load();
          }}
        />
      }
    >
      {failed ? (
        <p className="meta-line meta-line--danger">无法读取风险记录，请到项目风险页面查看。</p>
      ) : summary ? (
        <p className="meta-line">
          未关闭 {summary.total} 条：事实逾期 {summary.OVERDUE}、预测交付风险{" "}
          {summary.FORECAST_DELAY}、问题风险 {summary.ISSUE}、信息缺失 {summary.MISSING_DATA}
        </p>
      ) : null}

      {events.slice(0, 5).map((event) => (
        <div key={event.id}>
          <Space wrap>
            <Tag color={RISK_LEVEL_COLORS[event.level]}>{RISK_LEVEL_LABELS[event.level]}</Tag>
            <Tag>{RISK_TYPE_LABELS[event.event_type]}</Tag>
            <span>{event.title}</span>
          </Space>
          <p className="meta-line">
            {event.owner_name ? `责任人 ${event.owner_name}｜` : ""}
            依据 {event.evidence.length} 条
            {event.impact_date ? `｜影响日期 ${event.impact_date}` : ""}
          </p>
        </div>
      ))}
      {events.length > 5 ? (
        <p className="meta-line">另有 {events.length - 5} 条，请到风险页面查看。</p>
      ) : null}

      <Link href={`/projects/${projectId}/risks`}>打开风险与建议页面</Link>
    </AppCard>
  );
}
