"use client";

import type { ReactNode } from "react";
import { Button } from "antd";
import { ExclamationCircleOutlined, ReloadOutlined } from "@ant-design/icons";

type Props = {
  title?: string;
  description?: string;
  onRetry?: () => void;
  /** Extra actions (e.g. back to list) shown after / instead of retry. */
  action?: ReactNode;
};

export function ErrorState({
  title = "加载失败",
  description = "请检查网络连接后重试。",
  onRetry,
  action,
}: Props) {
  return (
    <div className="state-block" role="alert">
      <ExclamationCircleOutlined className="state-block__icon state-block__icon--error" />
      <span className="state-block__title">{title}</span>
      <span className="state-block__description">{description}</span>
      {onRetry ? (
        <Button icon={<ReloadOutlined />} onClick={onRetry}>
          重试
        </Button>
      ) : null}
      {action}
    </div>
  );
}
