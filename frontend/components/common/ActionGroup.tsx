import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
};

/** Consistent spacing/wrapping for page and card action button groups. */
export function ActionGroup({ children, className }: Props) {
  return (
    <div className={["action-group", className].filter(Boolean).join(" ")}>{children}</div>
  );
}
