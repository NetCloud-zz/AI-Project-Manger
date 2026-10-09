import type { ElementType, ReactNode } from "react";

type Props = {
  children: ReactNode;
  title?: ReactNode;
  /** Semantic heading level for the card title. Defaults to span for legacy cards. */
  titleLevel?: 2 | 3 | "span";
  extra?: ReactNode;
  footer?: ReactNode;
  /** Adds hover elevation; use for cards that link somewhere. */
  interactive?: boolean;
  /** Removes the drop shadow for cards nested inside another surface. */
  plain?: boolean;
  /** Stack direct children with a consistent gap. */
  stack?: "sm" | "md";
  as?: ElementType;
  className?: string;
};

export function AppCard({
  children,
  title,
  titleLevel = "span",
  extra,
  footer,
  interactive,
  plain,
  stack,
  as: Tag = "div",
  className,
}: Props) {
  const classes = [
    "app-card",
    interactive ? "app-card--interactive" : "",
    plain ? "app-card--plain" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  const body = stack ? <div className={`stack-${stack}`}>{children}</div> : children;
  const TitleTag: ElementType =
    titleLevel === 2 ? "h2" : titleLevel === 3 ? "h3" : "span";

  return (
    <Tag className={classes}>
      {title || extra ? (
        <div className="app-card__header">
          {title ? <TitleTag className="app-card__title">{title}</TitleTag> : <span />}
          {extra}
        </div>
      ) : null}
      {body}
      {footer ? <div className="app-card__footer">{footer}</div> : null}
    </Tag>
  );
}
