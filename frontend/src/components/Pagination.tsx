import { formatNumber } from "../utils/format";
import { Button } from "./Button";

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
  onLimitChange?: (limit: number) => void;
}

const PAGE_SIZES = [25, 50, 100];

export function Pagination({ total, limit, offset, onChange, onLimitChange }: PaginationProps) {
  const first = total === 0 ? 0 : offset + 1;
  const last = Math.min(offset + limit, total);
  return (
    <nav className="pagination" aria-label="Pagination">
      <span aria-live="polite">
        {total === 0 ? "No results" : `Showing ${formatNumber(first)}–${formatNumber(last)} of ${formatNumber(total)}`}
      </span>
      <div className="row">
        {onLimitChange ? (
          <label className="row small">
            Rows per page
            <select className="select" style={{ width: 80 }} value={limit} onChange={(event) => onLimitChange(Number(event.target.value))}>
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <Button size="sm" disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </Button>
        <Button size="sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Next
        </Button>
      </div>
    </nav>
  );
}
