"use client";

import { useState } from "react";
import { App, Button, Collapse, Input, Radio, Space, Table, Tag } from "antd";
import dayjs from "dayjs";

import { AppCard } from "@/components/common/AppCard";
import { ApiError } from "@/lib/http";
import { adoptAdvice, evaluateAdvice, rejectAdvice } from "@/services/risks";
import {
  ADVICE_OUTCOME_LABELS,
  ADVICE_STATUS_COLORS,
  ADVICE_STATUS_LABELS,
  type AdviceOption,
  type AdviceRecord,
} from "@/types/advice";

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

const stamp = (value: string | null) => (value ? dayjs(value).format("YYYY-MM-DD HH:mm") : null);

function Bullets({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="meta-line">{title}</p>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function OptionTable({
  options,
  recommended,
}: {
  options: AdviceOption[];
  recommended: string | null;
}) {
  if (options.length === 0) return null;
  return (
    <Table<AdviceOption>
      size="small"
      pagination={false}
      rowKey={(row) => row.name}
      dataSource={options}
      columns={[
        {
          title: "方案",
          dataIndex: "name",
          render: (name: string) => (
            <Space>
              <strong>{name}</strong>
              {name === recommended ? <Tag color="blue">倾向方案</Tag> : null}
            </Space>
          ),
        },
        { title: "做法", dataIndex: "description" },
        {
          title: "时间影响",
          dataIndex: "time_impact_days",
          // A null estimate is a real answer: the evidence did not support a number.
          render: (value: number | null) =>
            value == null ? <span className="meta-line">无法估算</span> : `${value} 工作日`,
        },
        {
          title: "资源影响",
          dataIndex: "resource_impact",
          render: (value: string | null) => value ?? "—",
        },
        {
          title: "该方案的风险",
          dataIndex: "risks",
          render: (risks: string[]) => (risks.length ? risks.join("；") : "—"),
        },
      ]}
    />
  );
}

export function AdviceCard({
  record,
  onChanged,
}: {
  record: AdviceRecord;
  onChanged: (next: AdviceRecord) => void;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"none" | "adopt" | "reject" | "evaluate">("none");
  const [note, setNote] = useState("");
  const [actionTitles, setActionTitles] = useState("");
  const [outcome, setOutcome] = useState("EFFECTIVE");
  const [resolved, setResolved] = useState(true);

  const content = record.content;
  const decidable = record.status === "PROPOSED";

  const run = (call: () => Promise<AdviceRecord>, note: string) => {
    setBusy(true);
    call()
      .then((next) => {
        onChanged(next);
        setMode("none");
        setNote("");
        setActionTitles("");
        message.success(note);
      })
      .catch((error: unknown) => message.error(errorText(error)))
      .finally(() => setBusy(false));
  };

  const adopt = () =>
    run(
      () =>
        adoptAdvice(record.id, {
          note: note.trim() || null,
          actions: actionTitles
            .split("\n")
            .map((line) => line.trim())
            .filter((line) => line.length >= 2)
            .map((title) => ({ title })),
        }),
      "已记录采纳。计划日期不会因此改变，需要改期请走变更方案。",
    );

  return (
    <AppCard plain stack="sm">
      <Space wrap>
        <Tag color={ADVICE_STATUS_COLORS[record.status]}>
          {ADVICE_STATUS_LABELS[record.status]}
        </Tag>
        <Tag>第 {record.version} 版</Tag>
        <strong>{record.issue_title ?? `问题 #${record.issue_id}`}</strong>
        {record.content.escalation_recommended ? <Tag color="red">建议升级</Tag> : null}
      </Space>

      <p>{content.problem_summary}</p>

      <OptionTable options={content.options} recommended={content.recommended_option} />

      <Bullets title="可能原因（待验证假设）" items={content.possible_causes} />
      <Bullets title="需要核实" items={content.checks} />
      <Bullets title="建议的下一步" items={content.recommended_next_actions} />

      {content.data_gaps.length > 0 ? (
        <div>
          <p className="meta-line meta-line--danger">数据缺口，以下内容缺少依据：</p>
          <ul>
            {content.data_gaps.map((gap, index) => (
              <li key={`gap-${index}`}>{gap}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {content.suggested_participants.length > 0 ? (
        <p className="meta-line">建议参与：{content.suggested_participants.join("、")}</p>
      ) : null}

      <Collapse
        ghost
        size="small"
        items={[
          {
            key: "evidence",
            label: `依据 ${record.evidence.length} 条${
              record.coverage
                ? `（项目共 ${record.coverage.project_tasks_total} 个任务，执行中 ${record.coverage.execution_active_tasks} 个）`
                : ""
            }`,
            children: (
              <div className="stack-sm">
                {record.evidence.map((item, index) => (
                  <p key={`ev-${index}`} className="meta-line">
                    [{item.source_type}
                    {item.source_id ? `#${item.source_id}` : ""}
                    {item.updated_at ? ` @${dayjs(item.updated_at).format("MM-DD HH:mm")}` : ""}]{" "}
                    {item.detail}
                    {item.relevance ? `（${item.relevance}）` : ""}
                  </p>
                ))}
                {record.coverage ? (
                  <p className="meta-line">未纳入：{record.coverage.excluded.join("；")}</p>
                ) : null}
              </div>
            ),
          },
        ]}
      />

      <Space wrap className="meta-line">
        {stamp(record.generated_at) ? <span>生成 {stamp(record.generated_at)}</span> : null}
        {record.model ? <span>模型 {record.model}</span> : null}
        <span>AI 建议，非已确认结论</span>
      </Space>

      {record.decided_at ? (
        <p className="meta-line">
          {record.status === "ADOPTED" ? "采纳" : "处置"}于 {stamp(record.decided_at)}
          {record.decision_note ? `：${record.decision_note}` : ""}
        </p>
      ) : null}

      {record.action_items.length > 0 ? (
        <div>
          <p className="meta-line">由本建议产生的行动项：</p>
          <ul>
            {record.action_items.map((item) => (
              <li key={item.id}>
                {item.title}（{item.status}
                {item.due_date ? `，截止 ${item.due_date}` : ""}）
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {record.outcome ? (
        <p className="meta-line">
          效果评价：{ADVICE_OUTCOME_LABELS[record.outcome]}；问题
          {record.issue_resolved ? "已解决" : "仍未解决"}
          {record.outcome_note ? `。${record.outcome_note}` : ""}
        </p>
      ) : null}

      {mode === "adopt" ? (
        <div className="stack-sm">
          <Input.TextArea
            rows={2}
            value={note}
            placeholder="采纳说明，例如：采用外送方案，成本已确认"
            onChange={(e) => setNote(e.target.value)}
          />
          <Input.TextArea
            rows={3}
            value={actionTitles}
            placeholder="每行一个行动项，留空则只记录采纳。负责人和截止日期可稍后在行动项页面补充。"
            onChange={(e) => setActionTitles(e.target.value)}
          />
          <Space>
            <Button type="primary" loading={busy} onClick={adopt}>
              确认采纳
            </Button>
            <Button onClick={() => setMode("none")}>取消</Button>
          </Space>
        </div>
      ) : null}

      {mode === "reject" ? (
        <div className="stack-sm">
          <Input.TextArea
            rows={2}
            value={note}
            placeholder="不采纳的理由（必填）"
            onChange={(e) => setNote(e.target.value)}
          />
          <Space>
            <Button
              danger
              loading={busy}
              disabled={note.trim().length < 2}
              onClick={() => run(() => rejectAdvice(record.id, note.trim()), "已记录不采纳")}
            >
              确认不采纳
            </Button>
            <Button onClick={() => setMode("none")}>取消</Button>
          </Space>
        </div>
      ) : null}

      {mode === "evaluate" ? (
        <div className="stack-sm">
          <Radio.Group value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <Radio.Button value="EFFECTIVE">有效</Radio.Button>
            <Radio.Button value="PARTIAL">部分有效</Radio.Button>
            <Radio.Button value="INEFFECTIVE">无效</Radio.Button>
          </Radio.Group>
          <Radio.Group value={resolved} onChange={(e) => setResolved(e.target.value)}>
            <Radio.Button value={true}>问题已解决</Radio.Button>
            <Radio.Button value={false}>问题仍未解决</Radio.Button>
          </Radio.Group>
          <Input.TextArea
            rows={2}
            value={note}
            placeholder="实际发生了什么，例如：外送缩短 2 天，但方法转移仍在验证"
            onChange={(e) => setNote(e.target.value)}
          />
          <Space>
            <Button
              type="primary"
              loading={busy}
              onClick={() =>
                run(
                  () =>
                    evaluateAdvice(record.id, {
                      outcome,
                      issue_resolved: resolved,
                      note: note.trim() || null,
                    }),
                  "已记录效果评价",
                )
              }
            >
              保存评价
            </Button>
            <Button onClick={() => setMode("none")}>取消</Button>
          </Space>
        </div>
      ) : null}

      {mode === "none" ? (
        <Space wrap>
          {decidable ? (
            <>
              <Button type="primary" size="small" onClick={() => setMode("adopt")}>
                采纳并建行动项
              </Button>
              <Button size="small" onClick={() => setMode("reject")}>
                不采纳
              </Button>
            </>
          ) : null}
          {record.status === "ADOPTED" ? (
            <Button size="small" onClick={() => setMode("evaluate")}>
              {record.outcome ? "更新效果评价" : "记录效果"}
            </Button>
          ) : null}
        </Space>
      ) : null}
    </AppCard>
  );
}
