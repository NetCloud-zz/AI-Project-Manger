"use client";

import { useState } from "react";
import { App, Button, Collapse, Input, Space, Tag } from "antd";
import dayjs from "dayjs";

import { AppCard } from "@/components/common/AppCard";
import { ApiError } from "@/lib/http";
import { resolveRiskEvent } from "@/services/risks";
import {
  RISK_LEVEL_COLORS,
  RISK_LEVEL_LABELS,
  RISK_TYPE_LABELS,
  RISK_TYPE_MEANING,
  type RiskEvent,
} from "@/types/risk";

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
  return "操作未确认，请刷新后重试";
}

const day = (value: string | null) => (value ? dayjs(value).format("YYYY-MM-DD") : null);

function openFor(event: RiskEvent): string | null {
  if (!event.first_seen_at) return null;
  const days = dayjs().diff(dayjs(event.first_seen_at), "day");
  return days <= 0 ? "今天首次发现" : `已持续 ${days} 天`;
}

export function RiskEventRow({
  event,
  canResolve,
  onChanged,
}: {
  event: RiskEvent;
  canResolve?: boolean;
  onChanged: (next: RiskEvent) => void;
}) {
  const { message } = App.useApp();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState(false);

  const submit = () => {
    setBusy(true);
    resolveRiskEvent(event.id, note)
      .then((next) => {
        onChanged(next);
        setClosing(false);
        setNote("");
        message.success("已关闭。若检测条件仍然成立，下次扫描会重新打开");
      })
      .catch((error: unknown) => message.error(errorText(error)))
      .finally(() => setBusy(false));
  };

  return (
    <AppCard plain stack="sm">
      <Space wrap>
        <Tag color={RISK_LEVEL_COLORS[event.level]}>{RISK_LEVEL_LABELS[event.level]}</Tag>
        <Tag>{RISK_TYPE_LABELS[event.event_type]}</Tag>
        <strong>{event.title}</strong>
      </Space>

      <p className="meta-line">{RISK_TYPE_MEANING[event.event_type]}</p>
      <p>{event.cause}</p>

      <Space wrap className="meta-line">
        {event.owner_name ? <span>责任人 {event.owner_name}</span> : null}
        {event.impact_date ? <span>影响日期 {event.impact_date}</span> : null}
        {event.impact_days != null ? <span>偏差 {event.impact_days} 天</span> : null}
        {openFor(event) ? <span>{openFor(event)}</span> : null}
        {day(event.last_seen_at) ? <span>最近确认 {day(event.last_seen_at)}</span> : null}
      </Space>

      {event.evidence.length > 0 ? (
        <Collapse
          ghost
          size="small"
          items={[
            {
              key: "evidence",
              label: `依据 ${event.evidence.length} 条`,
              children: (
                <div className="stack-sm">
                  {event.evidence.map((item, index) => (
                    <p key={`${item.source_type}-${item.source_id}-${index}`} className="meta-line">
                      [{item.source_type}
                      {item.source_id ? `#${item.source_id}` : ""}
                      {item.updated_at ? ` @${dayjs(item.updated_at).format("MM-DD HH:mm")}` : ""}]{" "}
                      {item.detail}
                    </p>
                  ))}
                </div>
              ),
            },
          ]}
        />
      ) : null}

      {event.status === "RESOLVED" ? (
        <p className="meta-line">
          已关闭{day(event.resolved_at) ? `（${day(event.resolved_at)}）` : ""}：
          {event.resolution ?? "未填写依据"}
        </p>
      ) : null}

      {canResolve && event.status === "OPEN" ? (
        closing ? (
          <Space.Compact style={{ width: "100%" }}>
            <Input
              value={note}
              placeholder="关闭依据，例如：已与负责人确认，另行提改期方案"
              onChange={(e) => setNote(e.target.value)}
              onPressEnter={submit}
            />
            <Button type="primary" loading={busy} disabled={note.trim().length < 2} onClick={submit}>
              确认关闭
            </Button>
            <Button onClick={() => setClosing(false)}>取消</Button>
          </Space.Compact>
        ) : (
          <Button size="small" onClick={() => setClosing(true)}>
            关闭风险
          </Button>
        )
      ) : null}
    </AppCard>
  );
}

export function RiskEventList({
  events,
  canResolve,
  onChanged,
}: {
  events: RiskEvent[];
  canResolve?: boolean;
  onChanged: (next: RiskEvent) => void;
}) {
  return (
    <div className="stack-sm">
      {events.map((event) => (
        <RiskEventRow
          key={event.id}
          event={event}
          canResolve={canResolve}
          onChanged={onChanged}
        />
      ))}
    </div>
  );
}
