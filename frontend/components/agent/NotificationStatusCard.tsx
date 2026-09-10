"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Space, Tag } from "antd";
import { useRouter } from "next/navigation";

import { AppCard } from "@/components/common/AppCard";
import { NotificationList } from "@/components/notifications/NotificationList";
import { listMyNotifications, listProposalNotifications } from "@/services/notifications";
import {
  NOTIFICATION_STATUS_COLORS,
  NOTIFICATION_STATUS_LABELS,
  type NotificationStatus,
  type PlanNotification,
} from "@/types/notification";

const ORDER: NotificationStatus[] = ["QUEUED", "SENT", "ACKNOWLEDGED", "FAILED"];

/** Delivery state for one proposal, or the current user's own inbox. */
export function NotificationStatusCard({
  projectId,
  proposalId,
}: {
  projectId?: number;
  proposalId?: string;
}) {
  const router = useRouter();
  const [items, setItems] = useState<PlanNotification[]>([]);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    () =>
      (projectId && proposalId
        ? listProposalNotifications(projectId, proposalId)
        : listMyNotifications({ limit: 10 })
      )
        .then((rows) => {
          setItems(rows);
          setFailed(false);
        })
        .catch(() => setFailed(true))
        .finally(() => setLoading(false)),
    [projectId, proposalId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const onChanged = (next: PlanNotification) =>
    setItems((prev) => prev.map((item) => (item.id === next.id ? next : item)));

  if (failed) {
    return (
      <AppCard plain>
        <Space>
          <span>无法读取通知状态</span>
          <Button size="small" onClick={() => void load()}>
            重试
          </Button>
        </Space>
      </AppCard>
    );
  }
  if (loading && items.length === 0) return null;

  const counts = ORDER.map((status) => ({
    status,
    count: items.filter((item) => item.status === status).length,
  })).filter((entry) => entry.count > 0);

  return (
    <AppCard plain stack="sm" title={proposalId ? "通知发送情况" : "发给我的计划变更通知"}>
      {items.length === 0 ? (
        <p>暂无通知记录。</p>
      ) : (
        <Space wrap>
          {counts.map((entry) => (
            <Tag key={entry.status} color={NOTIFICATION_STATUS_COLORS[entry.status]}>
              {NOTIFICATION_STATUS_LABELS[entry.status]} {entry.count}
            </Tag>
          ))}
        </Space>
      )}
      <p className="meta-line">
        「渠道已接受」只说明消息发出去了，「已确认知悉」才是收件人本人在系统内点过确认。
      </p>
      <NotificationList items={items} canRetry={Boolean(proposalId)} onChanged={onChanged} />
      <Space wrap>
        <Button size="small" onClick={() => void load()}>
          刷新
        </Button>
        <Button size="small" onClick={() => router.push("/notifications")}>
          打开通知中心
        </Button>
      </Space>
    </AppCard>
  );
}
