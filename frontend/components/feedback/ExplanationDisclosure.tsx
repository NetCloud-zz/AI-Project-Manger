"use client";

import { useId, useState, type ReactNode } from "react";
import { DownOutlined, UpOutlined } from "@ant-design/icons";

type Props = {
  /** Short visible summary when collapsed. */
  summary: ReactNode;
  children: ReactNode;
  /** Default expanded state; ignored after user toggles. */
  defaultOpen?: boolean;
  /** Optional count shown next to the toggle, e.g. remaining blocks. */
  expandCount?: number;
  className?: string;
};

/**
 * Presentational disclosure for long explanations. Does not invent business
 * conclusions — callers supply both the summary and the full detail.
 */
export function ExplanationDisclosure({
  summary,
  children,
  defaultOpen = false,
  expandCount,
  className,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div className={["explanation-disclosure", className].filter(Boolean).join(" ")}>
      <div className="explanation-disclosure__summary">{summary}</div>
      <button
        type="button"
        className="explanation-disclosure__toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? (
          <>
            <UpOutlined /> 收起详情
          </>
        ) : (
          <>
            <DownOutlined /> 展开详情
            {typeof expandCount === "number" && expandCount > 0 ? `（${expandCount}）` : ""}
          </>
        )}
      </button>
      {open ? (
        <div id={panelId} className="explanation-disclosure__body">
          {children}
        </div>
      ) : null}
    </div>
  );
}
