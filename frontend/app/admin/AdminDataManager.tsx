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

const PAGE_SIZE = 10;
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
  const [rowToDelete, setRowToDelete] = useState<Record<string, unknown> | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

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

  const confirmDelete = useCallback((row: Record<string, unknown>) => {
    setRowToDelete(row);
  }, []);

  const executeDelete = useCallback(async () => {
    if (!activeTable || !rowToDelete?.id) return;
    
    setIsDeleting(true);
    setError("");
    setMessage("");
    try {
      await authedFetch(`${apiBase}/api/admin/data/${activeTable.name}/${rowToDelete.id}`, {
        method: "DELETE",
      });
      setMessage("Row deleted successfully.");
      setRowToDelete(null);
      loadRows(activeTable, offset);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Failed to delete row.");
    } finally {
      setIsDeleting(false);
    }
  }, [activeTable, apiBase, authedFetch, loadRows, offset, rowToDelete]);

  const cancelDelete = useCallback(() => {
    setRowToDelete(null);
  }, []);

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
    <section className="flex flex-col lg:flex-row min-h-[680px] gap-6 lg:gap-8">
      {isSidebarOpen ? (
        <aside className="w-full lg:w-[280px] shrink-0 surface-card rounded-[24px] p-5 border border-white/50 shadow-[0_8px_30px_rgba(0,0,0,0.04)] bg-white/60 backdrop-blur-xl animate-in slide-in-from-left-4 fade-in duration-200 h-fit self-start lg:sticky lg:top-8 z-20">
          <div className="mb-6 flex items-start justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-[var(--accent-primary)]">Structured Data</p>
              <h2 className="text-xl font-bold text-[var(--text-primary)] mt-1">Catalog Manager</h2>
            </div>
            <button type="button" onClick={() => setIsSidebarOpen(false)} className="p-2 rounded-xl bg-blue-500/10 text-[var(--accent-primary)] hover:bg-blue-500/20 transition-colors" title="Close Sidebar">
               <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          </div>
          <div className="max-h-[640px] space-y-5 overflow-y-auto pr-1">
            {Object.entries(groups).map(([group, tables]) => {
              const isExpanded = expandedGroups[group] ?? true;
              return (
              <div key={group} className="border border-slate-100 rounded-[16px] bg-white/40 p-2 shadow-sm">
                <button 
                  type="button" 
                  onClick={() => setExpandedGroups(prev => ({ ...prev, [group]: !(prev[group] ?? true) }))}
                  className="flex w-full items-center justify-between p-2 focus:outline-none group/btn transition-colors hover:bg-slate-50/80 rounded-xl"
                >
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-500 group-hover/btn:text-[var(--accent-primary)] transition-colors">{group}</p>
                  <svg className={`w-4 h-4 text-slate-400 transition-transform duration-300 ${isExpanded ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7"/></svg>
                </button>
                <div className={`overflow-hidden transition-all duration-300 ease-in-out ${isExpanded ? "max-h-[800px] opacity-100 mt-2" : "max-h-0 opacity-0"}`}>
                  <div className="space-y-1 pb-1">
                    {tables.map((table) => (
                      <button
                        key={table.name}
                        type="button"
                        onClick={() => {
                          setActiveTable(table);
                          setOffset(0);
                          setQuery("");
                          closeForm();
                          if (window.innerWidth < 1024) setIsSidebarOpen(false);
                        }}
                        className={`w-full rounded-[14px] px-4 py-3 text-left text-sm font-semibold transition-all duration-200 block ${
                          activeTable?.name === table.name
                            ? "bg-[var(--accent-primary)] text-white shadow-md shadow-blue-500/20"
                            : "text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)] hover:shadow-sm"
                        }`}
                      >
                        {table.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )})}
          </div>
        </aside>
      ) : (
        <aside className="w-full lg:w-auto shrink-0 flex justify-end lg:justify-start animate-in slide-in-from-left-2 fade-in duration-200 h-fit self-start lg:sticky lg:top-8 z-20">
           <button type="button" onClick={() => setIsSidebarOpen(true)} className="p-3 rounded-xl bg-white shadow-sm border border-white/50 text-[var(--accent-primary)] hover:bg-blue-50 transition-colors" title="Open Sidebar">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6h16M4 12h16M4 18h7"/></svg>
           </button>
        </aside>
      )}

      <div className="flex-1 min-w-0 surface-card rounded-[24px] p-6 lg:p-8 border border-white/50 shadow-[0_8px_30px_rgba(0,0,0,0.04)] bg-white/60 backdrop-blur-xl flex flex-col">
        {activeTable ? (
          <>
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <span className="inline-block px-3 py-1 rounded-full bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] text-xs font-bold uppercase tracking-wider mb-2">{activeTable.group}</span>
                <h2 className="text-2xl sm:text-3xl font-bold text-[var(--text-primary)] truncate">{activeTable.label}</h2>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--text-secondary)]">{activeTable.description}</p>
              </div>
              <button type="button" onClick={openCreate} className="primary-button rounded-[14px] px-5 py-2.5 text-sm whitespace-nowrap shadow-md hover:shadow-lg transition-all shrink-0">
                <span className="flex items-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
                  Add New Record
                </span>
              </button>
            </div>

            <div className="mt-8 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="relative flex-1 flex items-center">
                <svg className="absolute left-3.5 text-slate-400 z-10 pointer-events-none" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") loadRows(activeTable, 0);
                  }}
                  className="app-input w-full py-2.5 bg-white/80 focus:bg-white transition-colors"
                  style={{ paddingLeft: '2.5rem' }}
                  placeholder={`Search in ${activeTable.label}...`}
                />
              </div>
              <div className="flex gap-2 shrink-0">
                <button type="button" onClick={() => loadRows(activeTable, 0)} className="secondary-button rounded-[14px] px-5 py-2.5 text-sm font-medium bg-white hover:bg-slate-50 border-slate-200">
                  Search
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    loadRows(activeTable, 0);
                  }}
                  className="secondary-button rounded-[14px] px-4 py-2.5 text-sm font-medium bg-white hover:bg-slate-50 border-slate-200 flex items-center justify-center"
                  aria-label="Refresh"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
                </button>
              </div>
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
              <form onSubmit={handleSubmit} className="mt-6 rounded-2xl border border-blue-100 bg-blue-50/40 p-5 sm:p-6 shadow-inner animate-slide-in">
                <div className="mb-6 flex items-center justify-between gap-3 border-b border-blue-200/60 pb-4">
                  <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                    {editingRow ? (
                      <><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Edit Record</>
                    ) : (
                      <><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg> Add New Record</>
                    )}
                  </h3>
                  <button type="button" onClick={closeForm} className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 rounded-full transition-colors">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
                  </button>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  {activeTable.columns.map((column) => {
                    const label = humanize(column);
                    
                    // Auto-generate UUID for "id" column if creating
                    let defaultValue = inputValue(column, editingRow?.[column], activeTable);
                    if (column === "id" && !editingRow) {
                       try {
                         defaultValue = crypto.randomUUID();
                       } catch (e) {
                         defaultValue = `id_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
                       }
                    }

                    const isIdField = column === "id";
                    const isReadOnly = isIdField || activeTable.readonly?.includes(column);

                    const commonProps = {
                      name: column,
                      defaultValue,
                      className: `app-input ${isReadOnly ? "bg-slate-50 cursor-not-allowed text-slate-500 opacity-80" : ""}`,
                      required: activeTable.required.includes(column),
                      readOnly: isReadOnly,
                    };
                    return (
                      <label key={column} className={activeTable.textarea.includes(column) || activeTable.json.includes(column) ? "md:col-span-2" : ""}>
                        <span className="field-label flex items-center justify-between">
                          <span>
                            {label}
                            {activeTable.required.includes(column) ? " *" : ""}
                          </span>
                          {isIdField && !editingRow && (
                             <span className="text-[10px] uppercase text-blue-500 font-bold bg-blue-50 px-2 py-0.5 rounded-full">Auto-generated</span>
                          )}
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
                <button type="submit" disabled={isSaving} className="primary-button rounded-[14px] mt-5 px-5 py-3 text-sm shadow-md">
                  {isSaving ? "Saving..." : editingRow ? "Save changes" : "Create row"}
                </button>
              </form>
            ) : null}

            <div className="mt-8 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm flex flex-col min-w-0">
              <div className="overflow-x-auto w-full">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500 border-b border-slate-200/80">
                    <tr>
                      {visibleColumns.map((column) => (
                        <th key={column} className="px-4 py-3.5 font-bold">{humanize(column)}</th>
                      ))}
                      <th className="px-4 py-3.5 font-bold text-right sticky right-0 z-10 bg-slate-50 shadow-[-4px_0_10px_rgba(0,0,0,0.02)]">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {isLoading ? (
                      <tr>
                        <td colSpan={visibleColumns.length + 1} className="px-4 py-12 text-center text-slate-500">
                          <div className="flex flex-col items-center justify-center gap-3">
                            <div className="h-6 w-6 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                            <p>Loading records...</p>
                          </div>
                        </td>
                      </tr>
                    ) : rows.length === 0 ? (
                      <tr>
                        <td colSpan={visibleColumns.length + 1} className="px-4 py-12 text-center text-slate-500">
                          <div className="flex flex-col items-center justify-center gap-2">
                            <svg className="w-8 h-8 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m8.25 3v6.75m0 0l-3-3m3 3l3-3M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" /></svg>
                            <p>No records found in this table.</p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      rows.map((row) => (
                        <tr key={String(row.id)} className="transition-colors hover:bg-slate-50/50 group">
                          {visibleColumns.map((column) => (
                            <td key={column} className="max-w-[200px] sm:max-w-[300px] px-4 py-3.5 text-slate-600 truncate relative z-0">
                              <span title={String(displayValue(row[column]))} className="truncate block">{displayValue(row[column])}</span>
                            </td>
                          ))}
                          <td className="px-4 py-3.5 text-right sticky right-0 z-10 bg-white group-hover:bg-slate-50 transition-colors shadow-[-4px_0_10px_rgba(0,0,0,0.02)]">
                            <div className="flex justify-end gap-2">
                              <button type="button" onClick={() => { setEditingRow(row); setIsCreating(false); }} className="secondary-button rounded-[14px] px-3 py-1.5 text-xs font-semibold flex items-center gap-1.5 shadow-sm bg-white hover:bg-slate-50" title="Edit">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
                                <span>Edit</span>
                              </button>
                              <button type="button" onClick={() => confirmDelete(row)} className="rounded-[14px] px-3 py-1.5 text-xs font-semibold flex items-center gap-1.5 border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 hover:border-red-300 transition-colors shadow-sm" title="Delete">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/></svg>
                                <span>Delete</span>
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

            <div className="mt-5 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-slate-500 font-medium">
              <span>
                Showing <span className="text-slate-800">{rows.length ? offset + 1 : 0}-{offset + rows.length}</span> of <span className="text-slate-800">{count}</span> records
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => loadRows(activeTable, Math.max(0, offset - PAGE_SIZE))}
                  className="secondary-button rounded-[14px] px-4 py-2 text-sm font-medium bg-white hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={offset + PAGE_SIZE >= count}
                  onClick={() => loadRows(activeTable, offset + PAGE_SIZE)}
                  className="secondary-button rounded-[14px] px-4 py-2 text-sm font-medium bg-white hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white"
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

      {/* Custom Delete Confirmation Modal */}
      {rowToDelete && activeTable && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-6">
              <div className="w-12 h-12 rounded-full bg-red-100 text-red-600 flex items-center justify-center mb-4">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/></svg>
              </div>
              <h3 className="text-xl font-bold text-slate-900 mb-2">Delete Record</h3>
              <p className="text-sm text-slate-600 mb-6">
                Are you sure you want to delete <strong className="text-slate-900">"{displayValue(rowToDelete[activeTable.columns[0]] || rowToDelete.id)}"</strong>? This action cannot be undone and will permanently remove this data from the system.
              </p>
              <div className="flex items-center gap-3 justify-end">
                <button type="button" onClick={cancelDelete} disabled={isDeleting} className="secondary-button rounded-[14px] px-5 py-2.5 text-sm font-medium">
                  Cancel
                </button>
                <button type="button" onClick={executeDelete} disabled={isDeleting} className="rounded-[14px] px-5 py-2.5 text-sm font-semibold bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors shadow-md shadow-red-500/20">
                  {isDeleting ? "Deleting..." : "Yes, delete record"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
