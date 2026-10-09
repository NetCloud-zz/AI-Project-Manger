import { InboxOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

type Props = {
  title?: string;
  description?: string;
  action?: ReactNode;
  /** Compact empty state for detail-page secondary modules. */
  compact?: boolean;
};

export function EmptyState({
  title = "暂无数据",
  description,
  action,
  compact = false,
}: Props) {
  return (
    <div className={`state-block${compact ? " state-block--compact" : ""}`}>
      {compact ? null : <InboxOutlined className="state-block__icon" />}
      <span className="state-block__title">{title}</span>
      {description ? <span className="state-block__description">{description}</span> : null}
      {action}
    </div>
  );
}
