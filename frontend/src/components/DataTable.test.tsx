import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DataTable, type Column } from "./DataTable";

interface Row {
  id: string;
  name: string;
}

const columns: Column<Row>[] = [
  { key: "name", header: "Name", sortKey: "name", render: (row) => row.name },
  { key: "action", header: "Action", render: (row) => <button type="button">Act on {row.name}</button> },
];

describe("DataTable", () => {
  it("toggles sorting from descending to ascending and exposes aria-sort", async () => {
    const onSortChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<DataTable caption="Rows" columns={columns} rows={[{ id: "1", name: "a" }]} rowKey={(r) => r.id} onSortChange={onSortChange} />);
    await user.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith("-name");

    rerender(<DataTable caption="Rows" columns={columns} rows={[{ id: "1", name: "a" }]} rowKey={(r) => r.id} sort="-name" onSortChange={onSortChange} />);
    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "descending");
    await user.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith("name");
  });

  it("opens rows by click or keyboard but not when an inner control is used", async () => {
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    render(<DataTable caption="Rows" columns={columns} rows={[{ id: "1", name: "a" }]} rowKey={(r) => r.id} onRowClick={onRowClick} rowLabel={(r) => `Open ${r.name}`} />);
    await user.click(screen.getByRole("button", { name: "Act on a" }));
    expect(onRowClick).not.toHaveBeenCalled();
    await user.click(screen.getByText("a"));
    expect(onRowClick).toHaveBeenCalledTimes(1);
    screen.getByRole("row", { name: "Open a" }).focus();
    await user.keyboard("{Enter}");
    expect(onRowClick).toHaveBeenCalledTimes(2);
  });

  it("shows an empty state", () => {
    render(<DataTable caption="Rows" columns={columns} rows={[]} rowKey={(r: Row) => r.id} emptyTitle="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});
