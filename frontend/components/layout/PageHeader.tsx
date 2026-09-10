import Link from "next/link";
import { LeftOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

type Props = {
  title: string;
  subtitle?: string;
  backHref?: string;
  backLabel?: string;
  action?: ReactNode;
};

export function PageHeader({ title, subtitle, backHref, backLabel = "返回", action }: Props) {
  return (
    <header className="page-header">
      {backHref ? (
        <Link href={backHref} className="page-header__back">
          <LeftOutlined /> {backLabel}
        </Link>
      ) : null}
      <div className="page-header__row">
        <div className="page-header__text">
          <h1 className="page-header__title">{title}</h1>
          {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
        </div>
        {action ? <div className="page-header__action">{action}</div> : null}
      </div>
    </header>
  );
}
