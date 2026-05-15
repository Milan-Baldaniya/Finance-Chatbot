"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

type TableConfig = {
  name: string;
  label: string;
  group: string;
  description: string;
  columns: string[];
  required: string[];
  readonly: string[];
  textarea: string[];
  arrays: string[];
  booleans: string[];
  numbers: string[];
  dates: string[];
  json: string[];
  search: string[];
};

type AdminDataManagerProps = {
  apiBase: string;
  getAuthToken: () => Promise<string | null>;
  onUnauthorized: () => void;
};

const PAGE_SIZE = 25;
const SYSTEM_COLUMNS = ["id", "created_at", "updated_at", "performed_at", "completed_at"];

function humanize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function inputValue(column: string, value: unknown, table: TableConfig) {
  if (value === null || value === undefined) return "";
  if (table.arrays.includes(column) && Array.isArray(value)) return value.join(", ");
  if (table.json.includes(column)) return JSON.stringify(value, null, 2);
  return String(value);
}

function parseFormValue(column: string, rawValue: FormDataEntryValue | null, table: TableConfig) {
  if (table.booleans.includes(column)) return rawValue === "true";
  const value = String(rawValue ?? "").trim();
  if (!value) return null;
  if (table.arrays.includes(column)) {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (table.numbers.includes(column)) {
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue : null;
  }
  if (table.json.includes(column)) {
    try {
      return JSON.parse(value);
    } catch {
      throw new Error(`${humanize(column)} must be valid JSON.`);
    }
  }
  return value;
}

export default function AdminDataManager({ apiBase, getAuthToken, onUnauthorized }: AdminDataManagerProps) {
  const [groups, setGroups] = useState<Record<string, TableConfig[]>>({});
  const [activeTable, setActiveTable] = useState<TableConfig | null>(null);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [count, setCount] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [editingRow, setEditingRow] = useState<Record<string, unknown> | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const visibleColumns = useMemo(() => {
    if (!activeTable) return [];
    return [
      ...activeTable.columns.slice(0, 5),
      ...SYSTEM_COLUMNS.filter((column) => rows.some((row) => row[column] !== undefined)),
    ].filter((column, index, all) => all.indexOf(column) === index);
  }, [activeTable, rows]);

  const formTable = activeTable;
  const formRow = editingRow;

  const authedFetch = useCallback(
    async (url: string, init: RequestInit = {}) => {
      const token = await getAuthToken();
      if (!token) {
        onUnauthorized();
        throw new Error("Authentication is required.");
      }
      const response = await fetch(url, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          ...(init.headers || {}),
        },
      });
      if (response.status === 401) {
        onUnauthorized();
        throw new Error("Session expired.");
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Request failed.");
      }
      return data;
    },
    [getAuthToken, onUnauthorized],
  );

  const loadTables = useCallback(async () => {
    setError("");
    try {
      const data = await authedFetch(`${apiBase}/api/admin/data/tables`);
      setGroups(data.groups || {});
      const firstGroup = Object.values(data.groups || {})[0] as TableConfig[] | undefined;
      setActiveTable((current) => current || firstGroup?.[0] || null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load admin tables.");
    }
  }, [apiBase, authedFetch]);

  const loadRows = useCallback(
    async (table: TableConfig | null, nextOffset = 0) => {
      if (!table) return;
      setIsLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String(nextOffset),
        });
        if (query.trim()) params.set("q", query.trim());
        const data = await authedFetch(`${apiBase}/api/admin/data/${table.name}?${params.toString()}`);
        setRows(data.rows || []);
        setCount(data.count || 0);
        setOffset(nextOffset);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load rows.");
      } finally {
        setIsLoading(false);
      }
    },
    [apiBase, authedFetch, query],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadTables();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadTables]);

  useEffect(() => {
    if (!activeTable) return;
    const timer = window.setTimeout(() => {
      loadRows(activeTable, 0);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeTable, loadRows]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!formTable) return;

      setIsSaving(true);
      setError("");
      setMessage("");
      try {
        const formData = new FormData(event.currentTarget);
        const payload: Record<string, unknown> = {};
        for (const column of formTable.columns) {
          payload[column] = parseFormValue(column, formData.get(column), formTable);
        }

        const rowId = formRow?.id ? String(formRow.id) : "";
        const url = rowId
          ? `${apiBase}/api/admin/data/${formTable.name}/${rowId}`
          : `${apiBase}/api/admin/data/${formTable.name}`;
        await authedFetch(url, {
          method: rowId ? "PATCH" : "POST",
          body: JSON.stringify({ data: payload }),
        });
        setMessage(rowId ? "Row updated successfully." : "Row created successfully.");
        setEditingRow(null);
        setIsCreating(false);
        loadRows(formTable, offset);
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : "Failed to save row.");
      } finally {
        setIsSaving(false);
      }
    },
    [apiBase, authedFetch, formRow, formTable, loadRows, offset],
  );

  const handleDelete = useCallback(
    async (row: Record<string, unknown>) => {
      if (!activeTable || !row.id) return;
      const label = displayValue(row[activeTable.columns[0]] || row.id);
      if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;

      setError("");
      setMessage("");
      try {
        await authedFetch(`${apiBase}/api/admin/data/${activeTable.name}/${row.id}`, {
          method: "DELETE",
        });
        setMessage("Row deleted successfully.");
        loadRows(activeTable, offset);
      } catch (deleteError) {
        setError(deleteError instanceof Error ? deleteError.message : "Failed to delete row.");
      }
    },
    [activeTable, apiBase, authedFetch, loadRows, offset],
  );

  const openCreate = useCallback(() => {
    setEditingRow(null);
    setIsCreating(true);
    setMessage("");
    setError("");
  }, []);

  const closeForm = useCallback(() => {
    setEditingRow(null);
    setIsCreating(false);
  }, []);

  return (
    <section className="grid min-h-[680px] gap-5 lg:grid-cols-[280px_1fr]">
      <aside className="surface-card-strong rounded-[8px] p-4">
        <div className="mb-4">
          <p className="section-kicker">Structured Data</p>
          <h2 className="section-title mt-2">Catalog Manager</h2>
        </div>
        <div className="max-h-[640px] space-y-5 overflow-y-auto pr-1">
          {Object.entries(groups).map(([group, tables]) => (
            <div key={group}>
              <p className="mb-2 text-xs font-bold uppercase text-[var(--text-muted)]">{group}</p>
              <div className="space-y-1">
                {tables.map((table) => (
                  <button
                    key={table.name}
                    type="button"
                    onClick={() => {
                      setActiveTable(table);
                      setOffset(0);
                      setQuery("");
                      closeForm();
                    }}
                    className={`w-full rounded-[8px] px-3 py-2 text-left text-sm font-semibold transition ${
                      activeTable?.name === table.name
                        ? "bg-[rgba(0,123,229,0.10)] text-[var(--accent-primary)]"
                        : "text-[var(--text-secondary)] hover:bg-white"
                    }`}
                  >
                    {table.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </aside>

      <div className="surface-card-strong rounded-[8px] p-5">
        {activeTable ? (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="section-kicker">{activeTable.group}</p>
                <h2 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{activeTable.label}</h2>
                <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">{activeTable.description}</p>
              </div>
              <button type="button" onClick={openCreate} className="primary-button px-4 py-3 text-sm">
                Add row
              </button>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") loadRows(activeTable, 0);
                }}
                className="app-input min-w-[260px] flex-1"
                placeholder={`Search ${activeTable.label.toLowerCase()}`}
              />
              <button type="button" onClick={() => loadRows(activeTable, 0)} className="secondary-button px-4 py-3 text-sm">
                Search
              </button>
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  loadRows(activeTable, 0);
                }}
                className="secondary-button px-4 py-3 text-sm"
              >
                Refresh
              </button>
            </div>

            {error ? (
              <div className="mt-4 rounded-[8px] border border-[rgba(194,65,50,0.22)] bg-white/80 p-3 text-sm font-semibold text-[var(--error)]">
                {error}
              </div>
            ) : null}
            {message ? (
              <div className="mt-4 rounded-[8px] border border-[rgba(44,122,74,0.22)] bg-white/80 p-3 text-sm font-semibold text-[var(--success)]">
                {message}
              </div>
            ) : null}

            {isCreating || editingRow ? (
              <form onSubmit={handleSubmit} className="mt-5 rounded-[8px] border border-[var(--border-subtle)] bg-white/78 p-4">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-base font-semibold text-[var(--text-primary)]">
                    {editingRow ? "Edit row" : "Add row"}
                  </h3>
                  <button type="button" onClick={closeForm} className="secondary-button px-3 py-2 text-sm">
                    Close
                  </button>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  {activeTable.columns.map((column) => {
                    const label = humanize(column);
                    const defaultValue = inputValue(column, editingRow?.[column], activeTable);
                    const commonProps = {
                      name: column,
                      defaultValue,
                      className: "app-input",
                      required: activeTable.required.includes(column),
                    };
                    return (
                      <label key={column} className={activeTable.textarea.includes(column) || activeTable.json.includes(column) ? "md:col-span-2" : ""}>
                        <span className="field-label">
                          {label}
                          {activeTable.required.includes(column) ? " *" : ""}
                        </span>
                        {activeTable.booleans.includes(column) ? (
                          <select name={column} defaultValue={editingRow?.[column] === false ? "false" : "true"} className="app-input">
                            <option value="true">True</option>
                            <option value="false">False</option>
                          </select>
                        ) : activeTable.textarea.includes(column) || activeTable.json.includes(column) ? (
                          <textarea {...commonProps} rows={activeTable.json.includes(column) ? 7 : 4} />
                        ) : activeTable.dates.includes(column) ? (
                          <input {...commonProps} type={column.includes("_at") ? "datetime-local" : "date"} />
                        ) : (
                          <input {...commonProps} type={activeTable.numbers.includes(column) ? "number" : "text"} />
                        )}
                        {activeTable.arrays.includes(column) ? (
                          <span className="mt-1 block text-xs text-[var(--text-muted)]">Comma separated values.</span>
                        ) : null}
                      </label>
                    );
                  })}
                </div>
                <button type="submit" disabled={isSaving} className="primary-button mt-5 px-5 py-3 text-sm">
                  {isSaving ? "Saving..." : editingRow ? "Save changes" : "Create row"}
                </button>
              </form>
            ) : null}

            <div className="mt-5 overflow-hidden rounded-[8px] border border-[var(--border-subtle)] bg-white/74">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] border-collapse text-left text-sm">
                  <thead className="bg-[rgba(15,23,42,0.04)] text-xs uppercase text-[var(--text-muted)]">
                    <tr>
                      {visibleColumns.map((column) => (
                        <th key={column} className="px-3 py-3 font-bold">{humanize(column)}</th>
                      ))}
                      <th className="px-3 py-3 font-bold">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLoading ? (
                      <tr>
                        <td colSpan={visibleColumns.length + 1} className="px-3 py-8 text-center text-[var(--text-secondary)]">
                          Loading rows...
                        </td>
                      </tr>
                    ) : rows.length === 0 ? (
                      <tr>
                        <td colSpan={visibleColumns.length + 1} className="px-3 py-8 text-center text-[var(--text-secondary)]">
                          No rows found.
                        </td>
                      </tr>
                    ) : (
                      rows.map((row) => (
                        <tr key={String(row.id)} className="border-t border-[var(--border-subtle)] align-top">
                          {visibleColumns.map((column) => (
                            <td key={column} className="max-w-[260px] px-3 py-3 text-[var(--text-secondary)]">
                              <span className="line-clamp-3 break-words">{displayValue(row[column])}</span>
                            </td>
                          ))}
                          <td className="px-3 py-3">
                            <div className="flex gap-2">
                              <button type="button" onClick={() => { setEditingRow(row); setIsCreating(false); }} className="secondary-button px-3 py-2 text-xs">
                                Edit
                              </button>
                              <button type="button" onClick={() => handleDelete(row)} className="secondary-button px-3 py-2 text-xs text-[var(--error)]">
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--text-secondary)]">
              <span>
                Showing {rows.length ? offset + 1 : 0}-{offset + rows.length} of {count}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => loadRows(activeTable, Math.max(0, offset - PAGE_SIZE))}
                  className="secondary-button px-4 py-2 text-sm"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={offset + PAGE_SIZE >= count}
                  onClick={() => loadRows(activeTable, offset + PAGE_SIZE)}
                  className="secondary-button px-4 py-2 text-sm"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-[8px] border border-[var(--border-subtle)] bg-white/70 p-5 text-sm text-[var(--text-secondary)]">
            No managed tables are configured.
          </div>
        )}
      </div>
    </section>
  );
}
