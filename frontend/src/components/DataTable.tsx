import type { KeyboardEvent, MouseEvent, ReactNode } from "react";
import { cx } from "../utils/cx";
import { EmptyState, ErrorState, LoadingState } from "./States";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** API sort field; makes the header a sort toggle. */
  sortKey?: string;
  align?: "left" | "right";
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  caption: string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyMessage?: ReactNode;
  /** Current API sort expression, e.g. ``-created_at``. */
  sort?: string;
  onSortChange?: (sort: string) => void;
  onRowClick?: (row: T) => void;
  rowLabel?: (row: T) => string;
  compact?: boolean;
}

function nextSort(current: string | undefined, key: string): string {
  if (current === `-${key}`) return key;
  return `-${key}`;
}

const INTERACTIVE = "a, button, input, select, textarea, label";

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  loading = false,
  error,
  onRetry,
  emptyTitle = "Nothing to show",
  emptyMessage,
  sort,
  onSortChange,
  onRowClick,
  rowLabel,
  compact = false,
}: DataTableProps<T>) {
  const handleClick = (row: T) => (event: MouseEvent<HTMLTableRowElement>) => {
    if ((event.target as HTMLElement).closest(INTERACTIVE)) return;
    onRowClick?.(row);
  };
  const handleKey = (row: T) => (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRowClick?.(row);
    }
  };

  let body: ReactNode = null;
  if (error && !rows?.length) body = <ErrorState error={error} onRetry={onRetry} title="Could not load data" />;
  else if (loading && !rows) body = <LoadingState />;
  else if (!rows?.length) body = <EmptyState title={emptyTitle} message={emptyMessage} />;

  return (
    <div className="table-wrap" aria-busy={loading || undefined}>
      <table className={cx("table", compact && "table-compact")}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => {
              const active = sort === column.sortKey || sort === `-${column.sortKey}`;
              const ariaSort = !column.sortKey || !active ? undefined : sort?.startsWith("-") ? "descending" : "ascending";
              return (
                <th key={column.key} scope="col" className={cx(column.align === "right" && "num", column.className)} aria-sort={ariaSort}>
                  {column.sortKey && onSortChange ? (
                    <button type="button" className="sort-button" onClick={() => onSortChange(nextSort(sort, column.sortKey as string))}>
                      {column.header}
                      <span className="sort-indicator" aria-hidden="true">
                        {active ? (sort?.startsWith("-") ? "▼" : "▲") : "↕"}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        {body ? null : (
          <tbody>
            {rows?.map((row) => (
              <tr
                key={rowKey(row)}
                className={cx(onRowClick && "clickable")}
                onClick={onRowClick ? handleClick(row) : undefined}
                onKeyDown={onRowClick ? handleKey(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                aria-label={onRowClick && rowLabel ? rowLabel(row) : undefined}
              >
                {columns.map((column) => (
                  <td key={column.key} className={cx(column.align === "right" && "num", column.className)}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        )}
      </table>
      {body}
    </div>
  );
}
