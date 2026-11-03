import type { ReactNode } from "react";
import { cx } from "../utils/cx";

interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Remove body padding (tables run edge to edge). */
  flush?: boolean;
  id?: string;
}

export function Card({ title, subtitle, actions, children, className, flush = false, id }: CardProps) {
  return (
    <section className={cx("card", className)} id={id} aria-label={typeof title === "string" ? title : undefined}>
      {title || actions ? (
        <header className="card-header">
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          {actions ? <div className="row">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cx("card-body", flush && "flush")}>{children}</div>
    </section>
  );
}
