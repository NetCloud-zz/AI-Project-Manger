"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Space, Tag } from "antd";
import { AppCard } from "@/components/common/AppCard";
import { request } from "@/lib/http";
import type { CommandPlan } from "@/types/agent";

const labels: Record<string, string> = {
  SUCCEEDED: "成功",
  FAILED: "失败",
  BLOCKED: "依赖阻断",
  ROLLED_BACK: "已回滚",
  PENDING: "未执行",
  UNKNOWN: "中断未决",
};

const toolLabels: Record<string, string> = {
  get_current_user: "确认当前用户",
  create_project: "创建项目",
  update_project: "更新项目",
  create_task: "创建任务",
  create_milestone: "创建里程碑",
  update_task: "更新任务",
  draft_project_plan: "起草计划草案",
  apply_project_plan: "发布计划草案",
  list_projects: "查询项目列表",
  get_project: "查询项目",
  search_tasks: "搜索任务",
  batch_create_tasks: "批量创建任务",
  batch_update_tasks: "批量更新任务",
  batch_find_users: "批量查询负责人",
  find_users: "查询负责人",
  submit_progress: "提交进展",
  propose_change: "生成变更方案",
  execute_change_plan: "执行变更方案",
};

function toolLabel(tool?: string | null): string {
  if (!tool) return "";
  return toolLabels[tool] ?? tool;
}

export function CommandPlanCard({ initial }: { initial: CommandPlan }) {
  const [fetched, setFetched] = useState<CommandPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const plan =
    fetched && fetched.request_id === initial.request_id && fetched.revision >= initial.revision
      ? fetched
      : initial;
  const url = `/api/v1/agent/requests/${initial.request_id}/plan`;
  const unplanned =
    plan.unplanned || ["INVALID_PLAN", "NEEDS_INPUT", "PLANNING_FAILED"].includes(plan.status);
  const unplannedTitle =
    plan.status === "NEEDS_INPUT"
      ? "待补充信息，未执行业务操作"
      : plan.error_code === "COMMAND_MODEL_UNAVAILABLE"
        ? "模型未能完成清单整理，未执行业务操作"
        : plan.error_code === "COMMAND_PLAN_INVALID"
          ? "清单未通过校验，未执行业务操作"
          : "清单整理未完成，未执行业务操作";
  const retryIds = plan.items
    .filter((i) => ["PENDING", "FAILED", "BLOCKED", "ROLLED_BACK"].includes(i.state))
    .map((i) => i.item_id);
  useEffect(() => {
    let active = true;
    request<CommandPlan>(url)
      .then((value) => {
        if (active) setFetched(value);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [url]);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setFetched(await request<CommandPlan>(url));
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取失败");
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    setBusy(true);
    setError("");
    try {
      setFetched(
        await request<CommandPlan>(`${url}/retry`, {
          method: "POST",
          body: { expected_revision: plan.revision, item_ids: retryIds },
          timeoutMs: 120_000,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "恢复失败，请刷新核对状态");
    } finally {
      setBusy(false);
    }
  }
  const businessSucceeded = plan.business_succeeded ?? 0;
  const createdTaskCount = plan.created_task_count ?? 0;
  const createdMilestoneCount = plan.created_milestone_count ?? 0;
  const recovery = plan.recovery;
  return (
    <AppCard plain title="指令执行清单">
      {unplanned ? (
        <>
          <Alert
            type={plan.status === "NEEDS_INPUT" ? "info" : "warning"}
            title={unplannedTitle}
          />
          <p>
            {plan.error?.trim()
              ? plan.error.includes("原文映射")
                ? "人员或项目核对步骤的内部引用未对齐，任务尚未创建。原文已保留，无需为了内部字段改写清单。"
                : plan.error
              : plan.business_item_count
                ? `原文包含 ${plan.business_item_count} 个编号条目。执行步骤尚未确认。`
                : "原始指令已保留。执行步骤尚未确认。"}
          </p>
          {recovery?.hint ? <p>{recovery.hint}</p> : null}
          {plan.questions?.length ? (
            <ul>
              {plan.questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          ) : null}
          <details>
            <summary>查看原始条目</summary>
            <ol>
              {plan.requirements?.map((item) => (
                <li key={item.requirement_id}>{item.text}</li>
              ))}
            </ol>
          </details>
        </>
      ) : (
        <>
          <p>
            共 {plan.expected_count} 个执行步骤 · 步骤成功 {plan.succeeded}
            {typeof plan.business_succeeded === "number"
              ? ` · 业务写入步骤成功 ${businessSucceeded}`
              : ""}
            {` · 实际创建任务 ${createdTaskCount} 个`}
            {createdMilestoneCount > 0 ? ` · 里程碑 ${createdMilestoneCount} 个` : ""}
            {" "}· 未完成 {plan.remaining}
            {plan.needs_review ? " · 回读发现字段差异待核实" : ""}
            {typeof plan.business_item_count === "number" && plan.business_item_count > 0
              ? ` · 业务条目 ${plan.business_item_count}`
              : ""}
          </p>
          {plan.needs_review ? (
            <Alert type="warning" title="结果待核实：已写入对象与计划字段存在差异，请先核对，勿重复创建。" />
          ) : null}
          {recovery?.hint && recovery.action !== "retry_pending" ? (
            <Alert
              type={recovery.action === "manual_verify" ? "warning" : "info"}
              title={recovery.hint}
            />
          ) : null}
        </>
      )}
      {!unplanned ? (
        <p>{plan.policy === "atomic" ? "全成全败" : "独立项继续，依赖项等待前置成功"}</p>
      ) : null}
      {!unplanned || plan.items.length > 0 ? (
        <ol>
          {plan.items.map((item) => (
            <li key={item.item_id}>
              <Tag
                color={
                  item.state === "SUCCEEDED"
                    ? "green"
                    : item.state === "UNKNOWN"
                      ? "orange"
                      : "default"
                }
              >
                {labels[item.state] ?? item.state}
              </Tag>{" "}
              {toolLabel(item.tool) ? <strong>{toolLabel(item.tool)}</strong> : null}
              {toolLabel(item.tool) ? " · " : null}
              {item.source_text}
              {item.result?.error && <p>{item.result.error.message}</p>}
            </li>
          ))}
        </ol>
      ) : null}
      {error && <Alert type="error" title={error} />}
      <Space>
        <Button loading={busy} onClick={refresh}>
          刷新状态
        </Button>
        {unplanned && plan.source && (
          <Button
            disabled={busy}
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("agent:restore-command", { detail: plan.source }),
              )
            }
          >
            补充／重新整理
          </Button>
        )}
        {["PARTIAL", "FAILED", "PAUSED", "READY"].includes(plan.status) &&
          retryIds.length > 0 &&
          !plan.needs_review && (
            <Button disabled={busy} onClick={retry}>
              恢复未完成项
            </Button>
          )}
      </Space>
      {unplanned && (
        <p>补充会将原文放回输入框；修改并发送后生成新请求，不会自动执行原请求。</p>
      )}
    </AppCard>
  );
}
