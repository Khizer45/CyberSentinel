import { describe, expect, it } from "vitest";
import { normalizeColumnName, parseCsv, readFileHead, rowsToRecords } from "./csv";

describe("parseCsv", () => {
  it("handles quotes, escaped quotes, CRLF and a BOM", () => {
    const parsed = parseCsv('﻿a,b,c\r\n1,"x, y","say ""hi"""\r\n2,,3\r\n');
    expect(parsed.header).toEqual(["a", "b", "c"]);
    expect(parsed.rows).toEqual([
      ["1", "x, y", 'say "hi"'],
      ["2", "", "3"],
    ]);
    expect(parsed.truncated).toBe(false);
  });

  it("stops after maxRows and reports truncation", () => {
    const parsed = parseCsv("h\n1\n2\n3\n4\n", 2);
    expect(parsed.rows).toEqual([["1"], ["2"]]);
    expect(parsed.truncated).toBe(true);
  });

  it("keeps quoted newlines inside a field", () => {
    const parsed = parseCsv('a,b\n"line1\nline2",2');
    expect(parsed.rows).toEqual([["line1\nline2", "2"]]);
  });
});

describe("normalizeColumnName", () => {
  it("matches the backend normalization", () => {
    expect(normalizeColumnName(" Flow Bytes/s")).toBe("flow_bytes_s");
    expect(normalizeColumnName("Src IP")).toBe("src_ip");
    expect(normalizeColumnName("﻿Label")).toBe("label");
  });
});

describe("rowsToRecords", () => {
  it("converts numbers, blanks and non-finite values and drops excluded columns", () => {
    const result = rowsToRecords(
      ["dur", "proto", "Flow Bytes/s", "Label"],
      [
        ["0.5", "tcp", "Infinity", "DoS"],
        ["", "udp", "1e3", "Benign"],
      ],
      new Set(["label"]),
    );
    expect(result.records).toEqual([
      { dur: 0.5, proto: "tcp", "Flow Bytes/s": null },
      { dur: null, proto: "udp", "Flow Bytes/s": 1000 },
    ]);
    expect(result.excludedColumns).toEqual(["Label"]);
    expect(result.nonFiniteValues).toBe(1);
  });
});

describe("readFileHead", () => {
  it("reads only complete lines from the start of a large file", async () => {
    const text = `${"a,b\n"}${"1,2\n".repeat(50)}`;
    const head = await readFileHead(new Blob([text]), 21);
    expect(head.split("\n").every((line) => line === "a,b" || line === "1,2")).toBe(true);
  });
});
