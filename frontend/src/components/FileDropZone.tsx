import { useRef, useState } from "react";
import { cx } from "../utils/cx";
import { Icon } from "./Icon";

interface FileDropZoneProps {
  onFile: (file: File) => void;
  accept?: string;
  disabled?: boolean;
  hint?: string;
}

export function FileDropZone({ onFile, accept = ".csv,text/csv", disabled = false, hint }: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const open = () => {
    if (!disabled) inputRef.current?.click();
  };
  return (
    <div
      className={cx("dropzone", dragging && "dragging")}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled || undefined}
      aria-label="Choose a CSV file to upload"
      onClick={open}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        const file = event.dataTransfer.files[0];
        if (file && !disabled) onFile(file);
      }}
    >
      <Icon name="upload" />
      <strong>Drop a CSV file here, or click to browse</strong>
      {hint ? <span className="small">{hint}</span> : null}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        aria-label="CSV file"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}
