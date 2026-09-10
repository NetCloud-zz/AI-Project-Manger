"use client";

import { useState } from "react";
import { App, Button, Space, Tag } from "antd";
import dayjs from "dayjs";

import Link from "next/link";

import { AppCard } from "@/components/common/AppCard";
import { ApiError } from "@/lib/http";
import { acknowledgeNotification, retryNotification } from "@/services/notifications";
import {
  NOTIFICATION_EVENT_COLORS,
  NOTIFICATION_EVENT_LABELS,
  NOTIFICATION_STATUS_COLORS,
  NOTIFICATION_STATUS_LABELS,
  type PlanNotification,
} from "@/types/notification";
import { RISK_LEVEL_COLORS, RISK_LEVEL_LABELS, RISK_TYPE_LABELS } from "@/types/risk";

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

const time = (value: string | null) => (value ? dayjs(value).format("MM-DD HH:mm") : null);

export function NotificationRow({
  item,
  canRetry,
  onChanged,
}: {
  item: PlanNotification;
  /** Resending is a plan-manager action; the API rejects it for everyone else. */
  canRetry?: boolean;
  onChanged: (next: PlanNotification) => void;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<PlanNotification>, note: string) => {
    setBusy(true);
    try {
      onChanged(await action());
      message.success(note);
    } catch (error) {
      message.error(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppCard plain stack="sm">
      <Space wrap>
        <Tag color={NOTIFICATION_EVENT_COLORS[item.event_type]}>
          {NOTIFICATION_EVENT_LABELS[item.event_type]}
        </Tag>
        <Tag color={NOTIFICATION_STATUS_COLORS[item.status]}>
          {NOTIFICATION_STATUS_LABELS[item.status]}
        </Tag>
        <strong>
          {item.project_name ?? `项目 #${item.project_id}`}
          {item.project_code ? `（${item.project_code}）` : ""}
        </strong>
        <span className="meta-line">收件人 {item.recipient_name}</span>
        <span className="meta-line">
          {item.channel}
          {item.simulated ? "（本地模拟，未真实发送）" : ""}
        </span>
      </Space>

      {item.risk ? <RiskBody item={item} /> : null}
      {item.reason ? <p>变更原因：{item.reason}</p> : null}
      {item.operator_name ? <p className="meta-line">操作人：{item.operator_name}</p> : null}
      {item.project ? (
        <p>
          项目目标日期：{item.project.before.target_date ?? "未设置"} →{" "}
          {item.project.after.target_date ?? "未设置"}
        </p>
      ) : null}
      {item.forecast_finish_date ? <p>预测完成日期：{item.forecast_finish_date}</p> : null}
      {item.tasks.map((task) => (
        <p key={task.task_id}>
          {task.is_new ? "新增 " : ""}
          {task.task_name ?? `任务 #${task.task_id}`}：
          {task.is_new
            ? `${task.start_date ?? "未定"} ~ ${task.due_date ?? "未定"}`
            : `${task.before_due_date ?? "未定"} → ${task.due_date ?? "未定"}`}
        </p>
      ))}

      <Space wrap className="meta-line">
        {time(item.created_at) ? <span>生成 {time(item.created_at)}</span> : null}
        {time(item.sent_at) ? <span>发出 {time(item.sent_at)}</span> : null}
        {time(item.acknowledged_at) ? <span>确认 {time(item.acknowledged_at)}</span> : null}
        {item.status === "QUEUED" && time(item.next_attempt_at) ? (
          <span>下次尝试 {time(item.next_attempt_at)}</span>
        ) : null}
        {item.attempts > 0 ? <span>已尝试 {item.attempts} 次</span> : null}
      </Space>

      {item.delivery_uncertain ? (
        <p className="meta-line meta-line--danger">
          渠道未回应，这条通知可能已送达也可能没有，请勿据此判断对方是否知情。
        </p>
      ) : null}
      {item.status === "FAILED" && item.last_error ? (
        <p className="meta-line meta-line--danger">发送失败：{item.last_error}</p>
      ) : null}

      <Space wrap>
        {item.can_acknowledge ? (
          <Button
            type="primary"
            size="small"
            loading={busy}
            onClick={() =>
              void run(() => acknowledgeNotification(item.id), "已记录你确认知悉")
            }
          >
            确认知悉
          </Button>
        ) : null}
        {canRetry && item.status === "FAILED" ? (
          <Button
            size="small"
            loading={busy}
            onClick={() => void run(() => retryNotification(item.id), "已重新排队，稍后自动发送")}
          >
            重新发送
          </Button>
        ) : null}
      </Space>
    </AppCard>
  );
}

function RiskBody({ item }: { item: PlanNotification }) {
  const risk = item.risk!;
  const resolved = item.event_type === "RISK_RESOLVED";
  return (
    <>
      <Space wrap>
        <Tag>{RISK_TYPE_LABELS[risk.risk_type]}</Tag>
        <Tag color={resolved ? "green" : RISK_LEVEL_COLORS[risk.level]}>
          {resolved ? "已关闭" : RISK_LEVEL_LABELS[risk.level]}
        </Tag>
        {risk.is_prediction ? <Tag color="purple">预测</Tag> : <Tag color="default">事实</Tag>}
      </Space>
      <p>{risk.title}</p>
      {resolved ? (
        <p className="meta-line">关闭依据：{risk.resolution ?? "检测条件不再成立"}</p>
      ) : (
        <>
          {risk.cause ? <p className="meta-line">判断依据：{risk.cause}</p> : null}
          {risk.impact_date ? (
            <p className="meta-line">
              {risk.is_prediction ? "预测完成" : "涉及日期"}：{risk.impact_date}
              {risk.impact_days ? `（晚 ${risk.impact_days} 天）` : ""}
            </p>
          ) : null}
          {risk.kind_note ? <p className="meta-line">{risk.kind_note}</p> : null}
        </>
      )}
      <Link href={`/projects/${item.project_id}/risks`}>查看风险与建议</Link>
    </>
  );
}

export function NotificationList({
  items,
  canRetry,
  onChanged,
}: {
  items: PlanNotification[];
  canRetry?: boolean;
  onChanged: (next: PlanNotification) => void;
}) {
  return (
    <div className="stack-sm">
      {items.map((item) => (
        <NotificationRow key={item.id} item={item} canRetry={canRetry} onChanged={onChanged} />
      ))}
    </div>
  );
}
