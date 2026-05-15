"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/utils/supabase/client";
import AdminDataManager from "./AdminDataManager";

type Summary = {
  total_documents: number;
  processed_documents: number;
  warning_documents: number;
  failed_documents: number;
  needs_ocr_documents: number;
  embedding_pending_documents: number;
  embedding_failed_documents: number;
  total_chunks: number;
  embedded_chunks: number;
  pending_embeddings: number;
};

type DocumentInfo = {
  id: string;
  title: string;
  file_name: string;
  source_group?: string | null;
  status: string;
  total_pages: number;
  total_chunks: number;
  embedded_chunks: number;
  uploaded_at: string;
  processed_at?: string | null;
};

type UploadResult = {
  file: string;
  ok: boolean;
  message: string;
  status?: string;
  total_chunks?: number;
  embedded_chunks?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function statusTone(status: string) {
  if (status === "processed") return "text-[var(--success)]";
  if (status.includes("failed") || status === "needs_ocr") return "text-[var(--error)]";
  if (status.includes("warning") || status.includes("pending")) return "text-[var(--warning)]";
  return "text-[var(--text-secondary)]";
}

function formatDate(value?: string | null) {
  if (!value) return "Not processed";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function AdminUploadClient({ userEmail }: { userEmail: string }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [sourceGroup, setSourceGroup] = useState("knowledge_base");
  const [domain, setDomain] = useState("finance");
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isMounted, setIsMounted] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [activeModule, setActiveModule] = useState<"ingestion" | "data">("ingestion");
  const [error, setError] = useState("");
  const [results, setResults] = useState<UploadResult[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();

  const getAuthToken = useCallback(async () => {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token || null;
  }, [supabase]);

  useEffect(() => {
    const mount = window.setTimeout(() => {
      setIsMounted(true);
    }, 0);

    return () => window.clearTimeout(mount);
  }, []);

  const fetchAdminData = useCallback(async () => {
    const token = await getAuthToken();
    if (!token) {
      router.push("/sign-in");
      return;
    }

    setError("");
    try {
      const [statusRes, docsRes] = await Promise.all([
        fetch(`${API_BASE}/api/documents/status`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_BASE}/api/documents`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (statusRes.status === 403 || docsRes.status === 403) {
        throw new Error(
          "The frontend recognizes this account as admin, but the backend does not. Add the same ADMIN_EMAILS or ADMIN_USER_IDS value to backend/.env and restart the backend server.",
        );
      }
      if (statusRes.status === 401 || docsRes.status === 401) {
        router.push("/sign-in");
        return;
      }
      if (!statusRes.ok || !docsRes.ok) {
        throw new Error("Could not load the document pipeline.");
      }

      setSummary(await statusRes.json());
      const docsPayload = await docsRes.json();
      setDocuments(docsPayload.documents || []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load admin data.");
    } finally {
      setIsLoading(false);
    }
  }, [getAuthToken, router]);

  useEffect(() => {
    const load = window.setTimeout(() => {
      fetchAdminData();
    }, 0);

    return () => window.clearTimeout(load);
  }, [fetchAdminData]);

  const handleUpload = useCallback(async () => {
    if (!files.length || isUploading) return;
    const token = await getAuthToken();
    if (!token) {
      router.push("/sign-in");
      return;
    }

    setIsUploading(true);
    setError("");
    setResults([]);

    const nextResults: UploadResult[] = [];
    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);
      if (files.length === 1 && title.trim()) formData.append("title", title.trim());
      formData.append("source_group", sourceGroup.trim() || "knowledge_base");
      formData.append("domain", domain.trim() || "finance");
      if (files.length === 1 && version.trim()) formData.append("version", version.trim());

      try {
        const res = await fetch(`${API_BASE}/api/documents/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          nextResults.push({
            file: file.name,
            ok: false,
            message: data.detail || "Upload failed.",
          });
        } else {
          nextResults.push({
            file: file.name,
            ok: true,
            message: data.message || "Uploaded, ingested, and embedded.",
            status: data.status,
            total_chunks: data.total_chunks,
            embedded_chunks: data.embedded_chunks,
          });
        }
      } catch (uploadError) {
        nextResults.push({
          file: file.name,
          ok: false,
          message: uploadError instanceof Error ? uploadError.message : "Upload failed.",
        });
      }
      setResults([...nextResults]);
    }

    setIsUploading(false);
    setFiles([]);
    setTitle("");
    setVersion("");
    if (inputRef.current) inputRef.current.value = "";
    fetchAdminData();
  }, [domain, fetchAdminData, files, getAuthToken, isUploading, router, sourceGroup, title, version]);

  const selectedSize = files.reduce((total, file) => total + file.size, 0);
  const handleUnauthorized = useCallback(() => router.push("/sign-in"), [router]);

  if (!isMounted) {
    return (
      <main className="min-h-screen px-4 py-5 md:px-8">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
          <header className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="section-kicker">Admin Console</p>
              <h1 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">
                Insurance knowledge control center
              </h1>
            </div>
            <span className="status-pill">{userEmail}</span>
          </header>
          <div className="surface-card-strong rounded-[8px] p-5 text-sm font-semibold text-[var(--text-secondary)]">
            Loading admin console...
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-4 py-5 md:px-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="section-kicker">Admin Console</p>
            <h1 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">
              Insurance knowledge control center
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="status-pill">{userEmail}</span>
            <button type="button" onClick={() => router.push("/")} className="secondary-button px-4 py-3 text-sm">
              Back to chat
            </button>
          </div>
        </header>

        {error ? (
          <div className="rounded-[16px] border border-[rgba(194,65,50,0.22)] bg-white/80 p-4 text-sm font-semibold text-[var(--error)]">
            {error}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 rounded-[8px] border border-[var(--border-subtle)] bg-white/70 p-2">
          {[
            ["ingestion", "PDF ingestion"],
            ["data", "Product & legal data"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveModule(key as "ingestion" | "data")}
              className={`rounded-[8px] px-4 py-2 text-sm font-semibold transition ${
                activeModule === key
                  ? "bg-[var(--accent-primary)] text-white"
                  : "text-[var(--text-secondary)] hover:bg-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {activeModule === "data" ? (
          <AdminDataManager apiBase={API_BASE} getAuthToken={getAuthToken} onUnauthorized={handleUnauthorized} />
        ) : (
          <>

        <section className="grid gap-3 md:grid-cols-4">
          {[
            ["Documents", summary?.total_documents ?? 0],
            ["Processed", summary?.processed_documents ?? 0],
            ["Chunks", summary?.total_chunks ?? 0],
            ["Pending embeddings", summary?.pending_embeddings ?? 0],
          ].map(([label, value]) => (
            <div key={label} className="surface-card-strong rounded-[8px] p-4">
              <p className="text-sm font-semibold text-[var(--text-secondary)]">{label}</p>
              <p className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">{value}</p>
            </div>
          ))}
        </section>

        <section className="grid min-h-0 gap-5 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="surface-card-strong rounded-[8px] p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h2 className="section-title">Upload PDFs</h2>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  Each file is saved, chunked, and embedded before the next one starts.
                </p>
              </div>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="secondary-button h-11 w-11 p-0"
                title="Choose PDFs"
                aria-label="Choose PDFs"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <path d="M17 8l-5-5-5 5" />
                  <path d="M12 3v12" />
                </svg>
              </button>
            </div>

            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              className="hidden"
              onChange={(event) => setFiles(Array.from(event.target.files || []))}
            />

            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="flex w-full flex-col items-center justify-center rounded-[8px] border border-dashed border-[var(--border-strong)] bg-white/70 px-4 py-8 text-center transition hover:border-[var(--accent-primary)] hover:bg-white"
            >
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                {files.length ? `${files.length} PDF selected` : "Choose PDF files"}
              </span>
              <span className="mt-2 text-xs text-[var(--text-secondary)]">
                {files.length ? `${(selectedSize / 1024 / 1024).toFixed(2)} MB total` : "PDF only"}
              </span>
            </button>

            <div className="mt-5 grid gap-4">
              <label>
                <span className="field-label">Title</span>
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  disabled={files.length > 1}
                  className="app-input"
                  placeholder={files.length > 1 ? "Generated from each filename" : "Optional document title"}
                />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label>
                  <span className="field-label">Source group</span>
                  <input value={sourceGroup} onChange={(event) => setSourceGroup(event.target.value)} className="app-input" />
                </label>
                <label>
                  <span className="field-label">Domain</span>
                  <input value={domain} onChange={(event) => setDomain(event.target.value)} className="app-input" />
                </label>
              </div>
              <label>
                <span className="field-label">Version</span>
                <input
                  value={version}
                  onChange={(event) => setVersion(event.target.value.replace(/[^0-9]/g, ""))}
                  disabled={files.length > 1}
                  className="app-input"
                  placeholder={files.length > 1 ? "Auto assigned for batches" : "Optional numeric version"}
                />
              </label>
            </div>

            <button
              type="button"
              onClick={handleUpload}
              disabled={!files.length || isUploading}
              className="primary-button mt-5 w-full px-5 py-3 text-sm"
            >
              {isUploading ? "Uploading and embedding..." : "Inject and embed PDFs"}
            </button>

            {results.length ? (
              <div className="mt-5 space-y-2">
                {results.map((result) => (
                  <div key={result.file} className="rounded-[8px] border border-[var(--border-subtle)] bg-white/74 p-3">
                    <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{result.file}</p>
                    <p className={`mt-1 text-sm ${result.ok ? "text-[var(--success)]" : "text-[var(--error)]"}`}>
                      {result.message}
                    </p>
                    {result.ok ? (
                      <p className="mt-1 text-xs text-[var(--text-secondary)]">
                        {result.status} · {result.embedded_chunks ?? 0}/{result.total_chunks ?? 0} chunks embedded
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="surface-card-strong min-h-[420px] rounded-[8px] p-5">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="section-title">Indexed documents</h2>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  {isLoading ? "Loading pipeline state" : `${documents.length} documents in the registry`}
                </p>
              </div>
              <button type="button" onClick={fetchAdminData} className="secondary-button px-4 py-3 text-sm">
                Refresh
              </button>
            </div>

            <div className="max-h-[560px] overflow-y-auto pr-1">
              {documents.length === 0 ? (
                <div className="rounded-[8px] border border-[var(--border-subtle)] bg-white/70 p-5 text-sm text-[var(--text-secondary)]">
                  No indexed documents yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {documents.map((doc) => (
                    <article key={doc.id} className="rounded-[8px] border border-[var(--border-subtle)] bg-white/76 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">{doc.title}</h3>
                          <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">{doc.file_name}</p>
                        </div>
                        <span className={`text-xs font-bold uppercase ${statusTone(doc.status)}`}>{doc.status}</span>
                      </div>
                      <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-[var(--text-secondary)]">
                        <span>{doc.total_pages} pages</span>
                        <span>{doc.total_chunks} chunks</span>
                        <span>{doc.embedded_chunks} embedded</span>
                      </div>
                      <p className="mt-3 text-xs text-[var(--text-muted)]">
                        Processed {formatDate(doc.processed_at)}
                      </p>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
          </>
        )}
      </div>
    </main>
  );
}
