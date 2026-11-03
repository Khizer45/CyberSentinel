import type { ReactNode } from "react";
import { Link } from "react-router";
import { usePageTitle } from "../hooks/usePageTitle";
import { Icon } from "./Icon";

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  back?: { to: string; label: string };
}

export function PageHeader({ title, description, actions, back }: PageHeaderProps) {
  usePageTitle(title);
  return (
    <div className="page-header">
      <div>
        {back ? (
          <Link to={back.to} className="back-link">
            <Icon name="back" size={14} /> {back.label}
          </Link>
        ) : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="row">{actions}</div> : null}
    </div>
  );
}
