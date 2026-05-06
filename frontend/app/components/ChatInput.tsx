"use client";

import { FormEvent, memo, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: (documentContext?: string, documentName?: string) => void;
  isLoading: boolean;
  getAuthToken: () => Promise<string | null>;
}

function ChatInput({ value, onChange, onSend, isLoading, getAuthToken }: ChatInputProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachedFile, setAttachedFile] = useState<{ name: string; content: string } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [showUploadHint, setShowUploadHint] = useState(false);
  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 220)}px`;
    }
  }, [value]);

  const openFilePicker = () => {
    // Show the hint banner, then open file picker
    setShowUploadHint(true);
    if (hintTimerRef.current) clearTimeout(hintTimerRef.current);
    hintTimerRef.current = setTimeout(() => setShowUploadHint(false), 6000);
    fileInputRef.current?.click();
  };

  const dismissHint = () => {
    setShowUploadHint(false);
    if (hintTimerRef.current) clearTimeout(hintTimerRef.current);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const token = await getAuthToken();
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/chat/parse-document`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });

      if (!res.ok) {
        const errText = await res.text();
        console.error("Backend error:", errText);
        throw new Error(`Upload failed: ${errText}`);
      }
      const data = await res.json();
      setAttachedFile({ name: data.filename, content: data.content });
      setShowUploadHint(false); // dismiss hint once file is selected
    } catch (error) {
      console.error(error);
      alert("Failed to parse document. Please try a different PDF or Word file.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removeAttachment = () => {
    setAttachedFile(null);
  };

  const handleSubmit = (e?: FormEvent) => {
    if (e) e.preventDefault();
    if (!value.trim() && !attachedFile) return;
    
    let docContext = undefined;
    let docName = undefined;
    if (attachedFile) {
      docContext = `[Attached Document: ${attachedFile.name}]\n${attachedFile.content}\n`;
      docName = attachedFile.name;
      setAttachedFile(null);
    }
    onSend(docContext, docName);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="shrink-0 border-t border-[var(--border-subtle)] bg-white/60 px-4 py-4 md:px-6 md:py-5">
      <div className="mx-auto max-w-4xl">
        {/* ── Upload limitation hint banner ── */}
        {showUploadHint && (
          <div
            className="mb-3 flex items-start gap-3 rounded-2xl px-4 py-3 text-sm"
            style={{
              background: "linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)",
              border: "1px solid #fcd34d",
              boxShadow: "0 2px 12px rgba(251,191,36,0.18)",
              animation: "slideDown 0.25s ease",
            }}
          >
            {/* Warning icon */}
            <div className="mt-0.5 shrink-0">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" fill="#f59e0b" stroke="#d97706" strokeWidth="1"/>
                <line x1="12" y1="9" x2="12" y2="13" stroke="white" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="12" cy="17" r="1" fill="white"/>
              </svg>
            </div>
            {/* Message */}
            <div className="flex-1">
              <p className="font-semibold text-amber-800 text-[13px]">Document Upload Limit</p>
              <p className="text-amber-700 text-[12px] mt-0.5 leading-relaxed">
                Currently supports up to <strong>~3,000 words (1–2 pages)</strong> due to AI API limits.
                We are working to increase this. For best results, upload short policy summaries or
                key sections rather than full documents.
              </p>
            </div>
            {/* Dismiss */}
            <button
              onClick={dismissHint}
              className="shrink-0 mt-0.5 text-amber-500 hover:text-amber-700 transition"
              aria-label="Dismiss"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
              </svg>
            </button>
          </div>
        )}

        {attachedFile && (
          <div className="mb-3 flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1.5 w-max">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span className="text-xs font-medium text-[var(--text-primary)] max-w-[200px] truncate">{attachedFile.name}</span>
            <button onClick={removeAttachment} className="ml-1 text-[var(--text-muted)] hover:text-red-500">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="surface-card-soft flex items-end gap-3 rounded-[28px] p-3">
            <button
              type="button"
              onClick={openFilePicker}
              disabled={isLoading || isUploading}
              className="mb-1 flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full text-[var(--text-muted)] transition hover:bg-black/5 hover:text-[var(--text-primary)] disabled:cursor-not-allowed"
              title="Attach Document (PDF, DOCX, TXT)"
            >
              {isUploading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--text-muted)] border-t-[var(--accent-primary)]"></div>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
              )}
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              className="hidden"
              accept=".pdf,.doc,.docx,.txt,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            />
            <textarea
              ref={inputRef}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about policy eligibility, regulations, waiting periods, or plan types..."
              rows={1}
              className="min-h-[56px] w-full resize-none bg-transparent px-2 py-3 text-[15px] leading-7 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
            />
            <button
              type="submit"
              disabled={(!value.trim() && !attachedFile) || isLoading}
              className="primary-button h-12 w-12 cursor-pointer rounded-full p-0 disabled:cursor-not-allowed"
              aria-label="Send message"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2 11 13" />
                <path d="M22 2 15 22 11 13 2 9l20-7Z" />
              </svg>
            </button>
          </div>
        </form>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-[var(--text-secondary)]">
          <p>Press Enter to send. Use Shift + Enter for a new line.</p>
          <p>Verify important compliance or underwriting details before acting.</p>
        </div>
      </div>
    </div>
  );
}

export default memo(ChatInput);
