"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Alert, Skeleton, Space, Tag, Tooltip } from "antd";

import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { ApiError } from "@/lib/http";
import { fetchProjectForecast } from "@/services/projects";
import {
  FORECAST_VERDICT_COLORS,
  FORECAST_VERDICT_LABELS,
  type ProjectForecast,
} from "@/types/forecast";

type Props = {
  projectId: number;
  /** Rendered only for people who can see the whole plan; the API enforces it too. */
  visible: boolean;
};

export function ProjectForecastCard({ projectId, visible }: Props) {
  const [data, setData] = useState<ProjectForecast | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "denied" | "failed">("loading");

  useEffect(() => {
    if (!visible) return;
    let alive = true;
    fetchProjectForecast(projectId)
      .then((result) => {
        if (!alive) return;
        setData(result);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setState(error instanceof ApiError && error.status === 403 ? "denied" : "failed");
      });
    return () => {
      alive = false;
    };
  }, [projectId, visible]);

  if (!visible || state === "denied") return null;
  if (state === "loading") {
    return (
      <AppCard>
        <Skeleton active paragraph={{ rows: 2 }} />
      </AppCard>
    );
  }
  if (state === "failed" || !data) {
    return (
      <AppCard>
        <SectionTitle>交付预测</SectionTitle>
        <p className="meta-line">暂时算不出预测，请稍后重试。已承诺的目标日期不受影响。</p>
      </AppCard>
    );
  }

  const variance = data.variance_calendar_days;
  return (
    <AppCard stack="sm">
      <SectionTitle extra={<Link href={`/projects/${projectId}/planning`}>去排期预览</Link>}>
        交付预测
      </SectionTitle>
      <Space wrap>
        <Tag color={FORECAST_VERDICT_COLORS[data.verdict]}>
          {FORECAST_VERDICT_LABELS[data.verdict]}
        </Tag>
        <Tag color="purple">预测</Tag>
        <span className="meta-line">基准日 {data.as_of}</span>
      </Space>

      {data.computable ? (
        <p className="detail-text">
          按当前计划预测完成：<strong>{data.predicted_finish_date}</strong>
          {data.target_date ? (
            <>
              ，目标日期 {data.target_date}
              {variance ? `（${variance > 0 ? "晚" : "早"} ${Math.abs(variance)} 天）` : "（持平）"}
            </>
          ) : null}
        </p>
      ) : (
        <Alert
          type="warning"
          showIcon
          message="当前数据算不出预测完成日期"
          description={
            data.conflicts[0]?.message ??
            "排期引擎没有返回结果，通常是依赖成环或计划字段缺失。先修好数据，再谈日期。"
          }
        />
      )}

      {data.critical_path.length > 0 ? (
        <>
          <p className="meta-line">
            关键路径 {data.critical_path.length} 项，这些任务没有机动时间：
          </p>
          <Space wrap>
            {data.critical_path.map((step) => (
              <Tooltip
                key={step.task_id}
                title={`${step.start_date} ~ ${step.finish_date}`}
              >
                <Tag color="red">{step.task_name}</Tag>
              </Tooltip>
            ))}
          </Space>
        </>
      ) : null}

      <p className="meta-line">
        预测由计划、依赖和工作日历推算，不改变已承诺的目标日期，也不计算人员容量约束。
      </p>
    </AppCard>
  );
}
