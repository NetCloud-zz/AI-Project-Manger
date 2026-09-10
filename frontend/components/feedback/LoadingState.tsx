import { Spin } from "antd";

type Props = {
  tip?: string;
};

export function LoadingState({ tip = "加载中…" }: Props) {
  return (
    <div className="state-block" role="status" aria-live="polite">
      <Spin />
      <span>{tip}</span>
    </div>
  );
}
