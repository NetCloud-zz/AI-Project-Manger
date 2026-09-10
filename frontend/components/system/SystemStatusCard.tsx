"use client";

import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Badge, Button, Descriptions, Space, Tag } from "antd";

import { AppCard } from "@/components/common/AppCard";
import { useRefresh } from "@/hooks/useRefresh";
import type { ComponentStatus, ReadinessResponse } from "@/types/health";

type BadgeStatus = "success" | "error" | "default";

const STATUS_META: Record<ComponentStatus, { badge: BadgeStatus; label: string }> = {
  up: { badge: "success", label: "正常" },
  down: { badge: "error", label: "不可用" },
  not_configured: { badge: "default", label: "未配置" },
};

const DEPENDENCY_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  llm: "LLM Gateway",
  wecom: "企业微信",
};

export function SystemStatusCard({ readiness }: { readiness: ReadinessResponse | null }) {
  const { refresh, pending } = useRefresh();

  const dependencyItems = Object.entries(readiness?.dependencies ?? {}).map(
    ([name, dependency]) => ({
      key: name,
      label: DEPENDENCY_LABELS[name] ?? name,
      children: (
        <>
          <Badge
            status={STATUS_META[dependency.status].badge}
            text={STATUS_META[dependency.status].label}
          />
          {dependency.detail ? <div className="meta-line">{dependency.detail}</div> : null}
        </>
      ),
    }),
  );

  return (
    <AppCard
      title="系统自检"
      extra={
        <Button size="small" icon={<ReloadOutlined />} onClick={refresh} loading={pending}>
          刷新
        </Button>
      }
    >
      {readiness ? (
        <Space direction="vertical" size="middle" className="full-width">
          <Space wrap>
            <Tag color={readiness.status === "ok" ? "green" : "orange"}>
              {readiness.status === "ok" ? "服务就绪" : "服务降级"}
            </Tag>
            <Tag>{readiness.environment}</Tag>
            <Tag>v{readiness.version}</Tag>
          </Space>
          <Descriptions column={1} size="small" bordered items={dependencyItems} />
        </Space>
      ) : (
        <Alert
          type="error"
          showIcon
          message="无法连接后端服务"
          description="请确认 backend 已启动，且 NEXT_PUBLIC_API_BASE_URL / INTERNAL_API_BASE_URL 配置正确。"
        />
      )}
    </AppCard>
  );
}
