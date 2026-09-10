import { InboxOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

type Props = {
  title?: string;
  description?: string;
  action?: ReactNode;
};

export function EmptyState({ title = "暂无数据", description, action }: Props) {
  return (
    <div className="state-block">
      <InboxOutlined className="state-block__icon" />
      <span className="state-block__title">{title}</span>
      {description ? <span className="state-block__description">{description}</span> : null}
      {action}
    </div>
  );
}
