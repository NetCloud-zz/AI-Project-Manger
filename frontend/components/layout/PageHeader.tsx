import Link from "next/link";
import { LeftOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

type Props = {
  title: ReactNode;
  /** Secondary identity line (e.g. project code). */
  subtitle?: ReactNode;
  /** Optional eyebrow / meta above the title (status chips, codes). */
  meta?: ReactNode;
  backHref?: string;
  backLabel?: string;
  action?: ReactNode;
};

export function PageHeader({
  title,
  subtitle,
  meta,
  backHref,
  backLabel = "返回",
  action,
}: Props) {
  return (
    <header className="page-header">
      {backHref ? (
        <Link href={backHref} className="page-header__back">
          <LeftOutlined aria-hidden /> {backLabel}
        </Link>
      ) : null}
      <div className="page-header__row">
        <div className="page-header__text">
          {meta ? <div className="page-header__meta">{meta}</div> : null}
          <h1 className="page-header__title">{title}</h1>
          {subtitle ? <div className="page-header__subtitle">{subtitle}</div> : null}
        </div>
        {action ? <div className="page-header__action">{action}</div> : null}
      </div>
    </header>
  );
}
