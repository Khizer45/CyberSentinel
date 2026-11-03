/** Save a Blob as a file via a temporary object URL (no data is sent anywhere). */
export function saveBlob(blob: Blob, filename: string): void {
  const printable = Array.from(filename, (char) => (char.charCodeAt(0) < 32 ? "_" : char)).join("");
  const safeName = printable.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 150) || "download";
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = safeName;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
