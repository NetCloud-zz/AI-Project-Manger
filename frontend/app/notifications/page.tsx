"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Segmented, Space } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { NotificationList } from "@/components/notifications/NotificationList";
import { listMyNotifications } from "@/services/notifications";
import type { NotificationStatus, PlanNotification } from "@/types/notification";

type Filter = "ALL" | "UNACKNOWLEDGED" | NotificationStatus;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "UNACKNOWLEDGED", label: "待我确认" },
  { value: "ALL", label: "全部" },
  { value: "ACKNOWLEDGED", label: "已确认" },
  { value: "FAILED", label: "发送失败" },
];

function NotificationsPageInner() {
  const [items, setItems] = useState<PlanNotification[]>([]);
  const [filter, setFilter] = useState<Filter>("UNACKNOWLEDGED");
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    () =>
      listMyNotifications({ limit: 200 })
        .then((rows) => {
          setItems(rows);
          setFailed(false);
        })
        .catch(() => setFailed(true))
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = () => {
    setLoading(true);
    void load();
  };

  const onChanged = (next: PlanNotification) =>
    setItems((prev) => prev.map((item) => (item.id === next.id ? next : item)));

  const visible = items.filter((item) => {
    if (filter === "ALL") return true;
    if (filter === "UNACKNOWLEDGED") return item.status !== "ACKNOWLEDGED";
    return item.status === filter;
  });
  const pending = items.filter((item) => item.status !== "ACKNOWLEDGED").length;

  return (
    <PageContainer>
      <PageHeader
        title="通知中心"
        subtitle={
          pending > 0
            ? `${pending} 条计划变更或风险提醒等待你确认知悉`
            : "计划变更与风险提醒都已确认"
        }
        action={
          <Button icon={<ReloadOutlined />} onClick={refresh}>
            刷新
          </Button>
        }
      />
      <Space wrap>
        <Segmented
          value={filter}
          onChange={(value) => setFilter(value as Filter)}
          options={FILTERS}
        />
      </Space>
      {failed ? (
        <ErrorState description="无法加载通知" onRetry={refresh} />
      ) : loading ? (
        <LoadingState tip="加载通知…" />
      ) : visible.length === 0 ? (
        <EmptyState
          title="没有通知"
          description="计划变更涉及你的任务、或你负责的工作出现风险时，通知会出现在这里。"
        />
      ) : (
        <NotificationList items={visible} onChanged={onChanged} />
      )}
    </PageContainer>
  );
}

export default function NotificationsPage() {
  return (
    <RequireAuth>
      <NotificationsPageInner />
    </RequireAuth>
  );
}
