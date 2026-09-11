"use client";

import { useEffect, useState } from "react";
import { Alert, Button, Space, Tag } from "antd";
import { AppCard } from "@/components/common/AppCard";
import { request } from "@/lib/http";
import type { CommandPlan } from "@/types/agent";

const labels: Record<string, string> = { SUCCEEDED: "成功", FAILED: "失败", BLOCKED: "依赖阻断", ROLLED_BACK: "已回滚", PENDING: "未执行" };

export function CommandPlanCard({ initial }: { initial: CommandPlan }) {
  const [fetched, setFetched] = useState<CommandPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const plan = fetched && fetched.request_id === initial.request_id && fetched.revision >= initial.revision ? fetched : initial;
  const url = `/api/v1/agent/requests/${initial.request_id}/plan`;
  useEffect(() => {
    let active = true;
    request<CommandPlan>(url).then((value) => { if (active) setFetched(value); }).catch(() => {});
    return () => { active = false; };
  }, [url]);
  async function refresh() {
    setBusy(true); setError("");
    try { setFetched(await request<CommandPlan>(url)); }
    catch (e) { setError(e instanceof Error ? e.message : "读取失败"); }
    finally { setBusy(false); }
  }
  async function retry() {
    setBusy(true); setError("");
    try {
      setFetched(await request<CommandPlan>(`${url}/retry`, { method: "POST", body: { expected_revision: plan.revision, item_ids: plan.items.filter((i) => ["PENDING", "FAILED", "BLOCKED", "ROLLED_BACK"].includes(i.state)).map((i) => i.item_id) }, timeoutMs: 120_000 }));
    } catch (e) { setError(e instanceof Error ? e.message : "恢复失败，请刷新核对状态"); }
    finally { setBusy(false); }
  }
  return <AppCard plain title="指令执行清单">
    <p>共 {plan.expected_count} 项 · 成功 {plan.succeeded} 项 · 未完成 {plan.remaining} 项</p>
    <p>{plan.policy === "atomic" ? "全成全败" : "独立项继续，依赖项等待前置成功"}</p>
    <ol>{plan.items.map((item) => <li key={item.item_id}>
      <Tag color={item.state === "SUCCEEDED" ? "green" : "default"}>{labels[item.state] ?? item.state}</Tag>
      {item.source_text}
      {item.result?.error && <p>{item.result.error.message}</p>}
    </li>)}</ol>
    {error && <Alert type="error" title={error} />}
    <Space><Button loading={busy} onClick={refresh}>刷新状态</Button>
      {["PARTIAL", "FAILED", "PAUSED", "READY"].includes(plan.status) && plan.remaining > 0 && <Button disabled={busy} onClick={retry}>恢复未完成项</Button>}
    </Space>
  </AppCard>;
}
