/**
 * Filters, sorting and pagination live in the URL query string so every list view can be bookmarked,
 * shared with a colleague (who still needs access) and restored with the browser's back button.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";

export type SearchValue = string | number | boolean | string[] | null | undefined;

export interface SearchState {
  get(key: string, fallback?: string): string;
  getAll(key: string): string[];
  getNumber(key: string, fallback: number): number;
  getBoolean(key: string): boolean | undefined;
  update(changes: Record<string, SearchValue>, options?: { resetPage?: boolean }): void;
  clear(keys: string[]): void;
}

export function useSearchState(): SearchState {
  const [search, setSearch] = useSearchParams();

  const update = useCallback(
    (changes: Record<string, SearchValue>, options: { resetPage?: boolean } = {}) => {
      setSearch(
        (previous) => {
          const next = new URLSearchParams(previous);
          for (const [key, value] of Object.entries(changes)) {
            next.delete(key);
            if (value === null || value === undefined || value === "" || value === false) continue;
            if (Array.isArray(value)) value.forEach((item) => next.append(key, item));
            else next.set(key, String(value));
          }
          if ((options.resetPage ?? true) && !("offset" in changes)) next.delete("offset");
          return next;
        },
        { replace: true },
      );
    },
    [setSearch],
  );

  return useMemo<SearchState>(
    () => ({
      get: (key, fallback = "") => search.get(key) ?? fallback,
      getAll: (key) => search.getAll(key),
      getNumber: (key, fallback) => {
        const raw = search.get(key);
        const value = raw === null ? Number.NaN : Number(raw);
        return Number.isFinite(value) ? value : fallback;
      },
      getBoolean: (key) => {
        const raw = search.get(key);
        return raw === "true" ? true : raw === "false" ? false : undefined;
      },
      update,
      clear: (keys) => update(Object.fromEntries(keys.map((key) => [key, null]))),
    }),
    [search, update],
  );
}
