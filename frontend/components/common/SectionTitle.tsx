import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  /** Right-aligned controls, e.g. a view switcher. */
  extra?: ReactNode;
  /** Removes the top margin when the title starts a column. */
  flush?: boolean;
  /** Heading level. Default h2 for page sections; use h3 inside cards. */
  level?: 2 | 3;
};

export function SectionTitle({ children, extra, flush, level = 2 }: Props) {
  const Tag = level === 3 ? "h3" : "h2";
  const title = (
    <Tag
      className={`section-title${level === 3 ? " section-title--sub" : ""}${
        flush && !extra ? " section-title--flush" : ""
      }`}
    >
      {children}
    </Tag>
  );

  if (!extra) return title;

  return (
    <div className={`section-header${flush ? " section-header--flush" : ""}`}>
      {title}
      {extra}
    </div>
  );
}
