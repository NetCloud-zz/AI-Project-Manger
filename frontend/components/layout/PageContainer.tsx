import type { ReactNode } from "react";

type Width = "default" | "narrow" | "form";

type Props = {
  children: ReactNode;
  /** `narrow` for detail pages, `form` for single-column forms. */
  width?: Width;
  /** Drop the bottom padding that clears the mobile tab bar. */
  flush?: boolean;
  className?: string;
};

const WIDTH_CLASS: Record<Width, string> = {
  default: "",
  narrow: "page-container--narrow",
  form: "page-container--form",
};

/** Owns page max-width, responsive gutters and overflow for every business page. */
export function PageContainer({ children, width = "default", flush, className }: Props) {
  const classes = [
    "page-container",
    WIDTH_CLASS[width],
    flush ? "page-container--flush" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return <main className={classes}>{children}</main>;
}
