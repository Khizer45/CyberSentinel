import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cx } from "../utils/cx";

interface BaseFieldProps {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  className?: string;
}

function useFieldIds(id: string | undefined, hint: ReactNode, error: string | null | undefined) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return { fieldId, hintId, errorId, describedBy };
}

function FieldMessages({ hint, error, hintId, errorId }: { hint: ReactNode; error?: string | null; hintId: string; errorId: string }) {
  return (
    <>
      {hint ? (
        <span id={hintId} className="field-hint">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={errorId} className="field-error">
          {error}
        </span>
      ) : null}
    </>
  );
}

export function TextField({ label, hint, error, className, id, ...inputProps }: BaseFieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const ids = useFieldIds(id, hint, error);
  return (
    <div className={cx("field", className)}>
      <label htmlFor={ids.fieldId}>{label}</label>
      <input id={ids.fieldId} className="input" aria-invalid={error ? true : undefined} aria-describedby={ids.describedBy} {...inputProps} />
      <FieldMessages hint={hint} error={error} hintId={ids.hintId} errorId={ids.errorId} />
    </div>
  );
}

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export function SelectField({
  label,
  hint,
  error,
  className,
  id,
  options,
  placeholder,
  ...selectProps
}: BaseFieldProps & SelectHTMLAttributes<HTMLSelectElement> & { options: SelectOption[]; placeholder?: string }) {
  const ids = useFieldIds(id, hint, error);
  return (
    <div className={cx("field", className)}>
      <label htmlFor={ids.fieldId}>{label}</label>
      <select id={ids.fieldId} className="select" aria-invalid={error ? true : undefined} aria-describedby={ids.describedBy} {...selectProps}>
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      <FieldMessages hint={hint} error={error} hintId={ids.hintId} errorId={ids.errorId} />
    </div>
  );
}

export function TextAreaField({ label, hint, error, className, id, ...areaProps }: BaseFieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ids = useFieldIds(id, hint, error);
  return (
    <div className={cx("field", className)}>
      <label htmlFor={ids.fieldId}>{label}</label>
      <textarea id={ids.fieldId} className="textarea" aria-invalid={error ? true : undefined} aria-describedby={ids.describedBy} {...areaProps} />
      <FieldMessages hint={hint} error={error} hintId={ids.hintId} errorId={ids.errorId} />
    </div>
  );
}

export function Checkbox({ label, ...inputProps }: { label: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="checkbox">
      <input type="checkbox" {...inputProps} />
      {label}
    </label>
  );
}

/** Multi-select filter rendered as toggle chips (e.g. risk bands, alert statuses). */
export function ChipGroup({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: SelectOption[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  return (
    <div className="field" role="group" aria-label={label}>
      <span className="field-label">{label}</span>
      <div className="chip-group">
        {options.map((option) => {
          const active = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              className="chip"
              aria-pressed={active}
              onClick={() => onChange(active ? selected.filter((value) => value !== option.value) : [...selected, option.value])}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
