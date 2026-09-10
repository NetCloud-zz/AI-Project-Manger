import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  /** Right-aligned controls, e.g. a view switcher. */
  extra?: ReactNode;
  /** Removes the top margin when the title starts a column. */
  flush?: boolean;
};

export function SectionTitle({ children, extra, flush }: Props) {
  const title = <h2 className={`section-title${flush && !extra ? " section-title--flush" : ""}`}>{children}</h2>;

  if (!extra) return title;

  return (
    <div className={`section-header${flush ? " section-header--flush" : ""}`}>
      {title}
      {extra}
    </div>
  );
}
