"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Skeleton, Space, Tag, Tooltip } from "antd";

import { ActionGroup } from "@/components/common/ActionGroup";
import { AppCard } from "@/components/common/AppCard";
import { SectionTitle } from "@/components/common/SectionTitle";
import { ExplanationDisclosure } from "@/components/feedback/ExplanationDisclosure";
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
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => {
    setState("loading");
    setReloadKey((value) => value + 1);
  }, []);

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
  }, [projectId, visible, reloadKey]);

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
        <ActionGroup>
          <Button onClick={reload}>重新加载</Button>
        </ActionGroup>
      </AppCard>
    );
  }

  const variance = data.variance_calendar_days;
  const visiblePath = data.critical_path.slice(0, 3);
  const hiddenPathCount = Math.max(0, data.critical_path.length - visiblePath.length);

  return (
    <AppCard stack="sm">
      <SectionTitle
        extra={
          <Button href={`/projects/${projectId}/planning`} size="small">
            去排期预览
          </Button>
        }
      >
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
        <ExplanationDisclosure
          summary={
            <div>
              <p className="meta-line">
                关键路径 {data.critical_path.length} 项，这些任务没有机动时间：
              </p>
              <Space wrap>
                {visiblePath.map((step) => (
                  <Tooltip
                    key={step.task_id}
                    title={`${step.start_date} ~ ${step.finish_date}`}
                  >
                    <Tag color="red">{step.task_name}</Tag>
                  </Tooltip>
                ))}
                {hiddenPathCount > 0 ? <Tag>+{hiddenPathCount} 项</Tag> : null}
              </Space>
            </div>
          }
          expandCount={hiddenPathCount > 0 ? hiddenPathCount : undefined}
          defaultOpen={false}
        >
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
        </ExplanationDisclosure>
      ) : (
        <p className="meta-line">
          预测由计划、依赖和工作日历推算，不改变已承诺的目标日期，也不计算人员容量约束。
        </p>
      )}
    </AppCard>
  );
}
