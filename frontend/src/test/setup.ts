import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Plotly needs a real browser layout engine; charts are exercised through their data-table fallback in tests.
vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn(() => Promise.resolve()), purge: vi.fn() },
}));

if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

if (!URL.createObjectURL) {
  Object.defineProperty(URL, "createObjectURL", { writable: true, value: vi.fn(() => "blob:test") });
  Object.defineProperty(URL, "revokeObjectURL", { writable: true, value: vi.fn() });
}

afterEach(() => {
  cleanup();
});
