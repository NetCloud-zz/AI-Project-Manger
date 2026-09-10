import Link from "next/link";
import { Button } from "antd";
import { CalendarOutlined, EditOutlined } from "@ant-design/icons";

import { AppCard } from "@/components/common/AppCard";
import { TaskStatusTag } from "@/components/project/StatusTags";
import type { Task } from "@/types/task";

type Props = {
  task: Task;
  showUpdateButton?: boolean;
};

export function TaskCard({ task, showUpdateButton = true }: Props) {
  const range =
    task.start_date && task.due_date
      ? `${task.start_date} → ${task.due_date}`
      : task.start_date
        ? `开始 ${task.start_date}`
        : task.due_date
          ? `截止 ${task.due_date}`
          : "日期未定";

  return (
    <AppCard as="article" interactive>
      <Link href={`/tasks/${task.id}`}>
        <div className="entity-card__code">
          {task.project?.project_code ?? `项目 #${task.project_id}`}
        </div>
        <div className="entity-card__name">
          {task.branch_label ? `[${task.branch_label}] ` : ""}
          {task.task_name}
        </div>
        <div className="meta-line meta-line--spaced">
          <CalendarOutlined /> {range}
        </div>
        <div className="chip-row">
          <TaskStatusTag status={task.status} />
        </div>
      </Link>
      {showUpdateButton ? (
        <Link href={`/tasks/${task.id}/update`} className="entity-card__action">
          <Button type="primary" block icon={<EditOutlined />}>
            更新进展
          </Button>
        </Link>
      ) : null}
    </AppCard>
  );
}
