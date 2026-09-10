"use client";

import Link from "next/link";
import { Alert, Button, Modal, Table } from "antd";

import type { ImpactedTask, ScheduleImpact } from "@/lib/schedule-impact";

type Props = {
  projectId: number;
  impact: ScheduleImpact | null;
  onClose: () => void;
  /** Provided when the caller can switch to the schedule preview in place. */
  onOpenPreview?: () => void;
};

const columns = [
  { title: "任务", dataIndex: "task_name", key: "task_name" },
  {
    title: "当前完成",
    key: "current",
    render: (_: unknown, row: ImpactedTask) => row.current_finish_date ?? "—",
  },
  {
    title: "会变成",
    key: "predicted",
    render: (_: unknown, row: ImpactedTask) => row.predicted_finish_date ?? "—",
  },
];

export function ScheduleImpactModal({ projectId, impact, onClose, onOpenPreview }: Props) {
  return (
    <Modal
      open={impact !== null}
      onCancel={onClose}
      title="这次修改会牵动其他任务"
      footer={[
        <Button key="close" onClick={onClose}>
          取消修改
        </Button>,
        onOpenPreview ? (
          <Button
            key="preview"
            type="primary"
            onClick={() => {
              onOpenPreview();
              onClose();
            }}
          >
            去排期预览
          </Button>
        ) : (
          <Link key="preview" href={`/projects/${projectId}/planning`}>
            <Button type="primary">去排期预览</Button>
          </Link>
        ),
      ]}
    >
      <Alert
        type="warning"
        showIcon
        message={impact?.detail}
        description="在排期预览里改同样的内容，可以看到完整差异、项目预测完成日期和通知范围，确认后一次性执行，不会留下半套数据。"
        style={{ marginBottom: 16 }}
      />
      <Table<ImpactedTask>
        size="small"
        rowKey="task_id"
        pagination={false}
        columns={columns}
        dataSource={impact?.impacted ?? []}
      />
    </Modal>
  );
}
