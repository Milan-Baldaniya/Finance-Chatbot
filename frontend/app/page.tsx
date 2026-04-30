"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createClient } from "@/utils/supabase/client";

interface SourceCitation {
  document_title: string;
  page_number: number | null;
  chunk_preview: string;
  relevance_score: number | null;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
  timestamp: Date;
}

interface Session {
  session_id: string;
  title: string;
  created_at: string;
}

interface ChatHistoryMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const SUGGESTIONS = [
  "What compliances are required before buying term insurance?",
  "What is the role of IRDAI?",
  "Explain KYC and underwriting.",
  "Can I buy insurance for my dependents?",
];

const sessionDateFormatter = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
});

const timeFormatter = new Intl.DateTimeFormat("en-IN", {
  hour: "numeric",
  minute: "2-digit",
});

function formatSessionDate(createdAt: string) {
  try {
    return sessionDateFormatter.format(new Date(createdAt));
  } catch {
    return "";
  }
}

function formatMessageTime(date: Date) {
  try {
    return timeFormatter.format(date);
  } catch {
    return "";
  }
}

function normalizeSessions(rawSessions: Session[]): Session[] {
  const byId = new Map<string, Session>();

  rawSessions.forEach((session) => {
    if (!byId.has(session.session_id)) {
      byId.set(session.session_id, session);
    }
  });

  const uniqueById = Array.from(byId.values()).sort(
    (left, right) =>
      new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
  );

  const deduped: Session[] = [];
  for (const session of uniqueById) {
    const duplicate = deduped.find((existing) => {
      if (existing.title.trim() !== session.title.trim()) {
        return false;
      }

      const timeDiff = Math.abs(
        new Date(existing.created_at).getTime() - new Date(session.created_at).getTime()
      );

      return timeDiff < 60_000;
    });

    if (!duplicate) {
      deduped.push(session);
    }
  }

  return deduped;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isDesktopSidebarOpen, setIsDesktopSidebarOpen] = useState(true);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string>("");
  const [checkingAuth, setCheckingAuth] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const supabaseRef = useRef<ReturnType<typeof createClient> | null>(null);
  const sendLockRef = useRef(false);
  const router = useRouter();

  const closeSidebar = useCallback(() => {
    if (typeof window !== "undefined" && window.innerWidth >= 768) {
      setIsDesktopSidebarOpen(false);
      return;
    }

    setIsSidebarOpen(false);
  }, []);

  const getSupabase = useCallback(() => {
    if (!supabaseRef.current) {
      supabaseRef.current = createClient();
    }

    return supabaseRef.current;
  }, []);

  const getAuthToken = useCallback(async (): Promise<string | null> => {
    const {
      data: { session },
    } = await getSupabase().auth.getSession();
    return session?.access_token || null;
  }, [getSupabase]);

  const fetchSessions = useCallback(async () => {
    const token = await getAuthToken();
    if (!token) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        return;
      }

      const data = await response.json();
      setSessions(normalizeSessions(data));
    } catch (error) {
      console.error("Failed to load sessions", error);
    }
  }, [getAuthToken]);

  useEffect(() => {
    const init = async () => {
      const {
        data: { user },
      } = await getSupabase().auth.getUser();

      if (!user) {
        router.push("/sign-in");
        return;
      }

      setUserEmail(user.email || "User");

      const token = await getAuthToken();
      if (token) {
        try {
          const response = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });

          if (response.ok) {
            const data = await response.json();
            if (!data.onboarding_completed) {
              router.push("/onboarding");
              return;
            }
          }
        } catch (error) {
          console.error("Error checking onboarding:", error);
        }
      }

      setCheckingAuth(false);

      fetchSessions();
    };

    init();
  }, [fetchSessions, getAuthToken, getSupabase, router]);

  const syncSessionHistory = useCallback(
    async (sid: string, options?: { closeSidebar?: boolean }) => {
      const token = await getAuthToken();
      if (!token) {
        return false;
      }

      try {
        const response = await fetch(`${API_BASE}/api/chat/${sid}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          return false;
        }

        const data = await response.json();
        const loadedMessages: Message[] = data.map((msg: ChatHistoryMessage) => ({
          id: msg.id || crypto.randomUUID(),
          role: msg.role,
          content: msg.content,
          timestamp: new Date(msg.created_at),
          sources: [],
        }));

        setMessages(loadedMessages);
        setSessionId(sid);

        if (options?.closeSidebar) {
          setIsSidebarOpen(false);
        }

        return true;
      } catch (error) {
        console.error("Failed to sync session history", error);
        return false;
      }
    },
    [getAuthToken]
  );

  const loadSession = async (sid: string) => {
    if (isLoading || deletingSessionId) {
      return;
    }

    await syncSessionHistory(sid, { closeSidebar: true });
  };

  const createNewChat = () => {
    if (isLoading) {
      return;
    }

    setMessages([]);
    setSessionId(null);
    setIsSidebarOpen(false);
    fetchSessions();
  };

  const handleDeleteSession = async (sid: string) => {
    if (isLoading || deletingSessionId) {
      return;
    }

    const token = await getAuthToken();
    if (!token) {
      router.push("/sign-in");
      return;
    }

    try {
      setDeletingSessionId(sid);

      const response = await fetch(`${API_BASE}/api/sessions/${sid}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        throw new Error("Delete session failed");
      }

      setSessions((prev) => prev.filter((session) => session.session_id !== sid));

      if (sessionId === sid) {
        setMessages([]);
        setSessionId(null);
      }
    } catch (error) {
      console.error("Failed to delete session", error);
    } finally {
      setDeletingSessionId(null);
    }
  };

  const handleLogout = async () => {
    await getSupabase().auth.signOut();
    router.push("/sign-in");
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 220)}px`;
    }
  }, [input]);

  const sendMessage = async (text?: string) => {
    const question = (text || input).trim();
    if (!question || isLoading || sendLockRef.current) {
      return;
    }

    sendLockRef.current = true;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    const token = await getAuthToken();
    if (!token) {
      sendLockRef.current = false;
      setIsLoading(false);
      router.push("/sign-in");
      return;
    }

    try {
      const currentSessionId = sessionId;
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question, session_id: currentSessionId }),
      });

      if (!response.ok) {
        throw new Error("Chat request failed");
      }

      const data = await response.json();
      const resolvedSessionId = data.session_id || currentSessionId;

      if (!currentSessionId && data.session_id) {
        setSessionId(data.session_id);
      }
      await fetchSessions();
      if (resolvedSessionId) {
        const synced = await syncSessionHistory(resolvedSessionId);
        if (!synced) {
          const botMsg: Message = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: data.answer,
            sources: data.sources,
            timestamp: new Date(data.created_at),
          };

          setMessages((prev) => [...prev, botMsg]);
        } else if (data.sources?.length) {
          setMessages((prev) => {
            const updated = [...prev];
            for (let index = updated.length - 1; index >= 0; index -= 1) {
              if (
                updated[index].role === "assistant" &&
                updated[index].content === data.answer
              ) {
                updated[index] = {
                  ...updated[index],
                  sources: data.sources,
                };
                break;
              }
            }
            return updated;
          });
        }
      }
    } catch {
      const errMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          "I could not reach the backend right now. Please check that the API server is running and try again.",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errMsg]);
    } finally {
      sendLockRef.current = false;
      setIsLoading(false);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    sendMessage();
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const sidebarContent = (
    <div className="surface-card flex h-full flex-col overflow-hidden p-4 md:p-5">
      <button
        type="button"
        onClick={createNewChat}
        disabled={isLoading}
        className="primary-button mb-4 w-full px-4 py-3 text-sm"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/18">
          +
        </span>
        Start a new chat
      </button>

      <div className="mb-3 flex items-center justify-between px-1">
        <div>
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Conversation history
          </p>
          <p className="text-xs text-[var(--text-secondary)]">
            {sessions.length} saved session{sessions.length === 1 ? "" : "s"}
          </p>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {sessions.length === 0 ? (
          <div className="surface-card-soft rounded-[22px] p-4 text-sm leading-6 text-[var(--text-secondary)]">
            Your saved chats will appear here once you start asking questions.
          </div>
        ) : (
          <div className="space-y-2">
            {sessions.map((session) => {
              const isActive = sessionId === session.session_id;
              const isDeleting = deletingSessionId === session.session_id;

              return (
                <div
                  key={session.session_id}
                  className={`w-full rounded-[20px] border px-4 py-3 text-left transition-all ${isActive
                      ? "border-[var(--accent-primary)] bg-[var(--accent-tertiary)] shadow-sm"
                      : "border-[var(--border-subtle)] bg-white/72 hover:border-[var(--border-focus)] hover:bg-white"
                    }`}
                >
                  <div className="flex items-start gap-3">
                    <button
                      type="button"
                      onClick={() => loadSession(session.session_id)}
                      disabled={isLoading || Boolean(deletingSessionId)}
                      className="min-w-0 flex-1 text-left disabled:cursor-not-allowed disabled:opacity-60"
                      title={session.title}
                    >
                      <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                        {session.title}
                      </p>
                      <div className="mt-1 flex items-center justify-between gap-3 text-xs text-[var(--text-secondary)]">
                        <span className="truncate">
                          {isActive ? "Currently open" : "Saved conversation"}
                        </span>
                        <span>{formatSessionDate(session.created_at)}</span>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleDeleteSession(session.session_id)}
                      disabled={isLoading || Boolean(deletingSessionId)}
                      className="secondary-button h-10 w-10 shrink-0 p-0 text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-60"
                      aria-label={`Delete ${session.title}`}
                      title={isDeleting ? "Deleting..." : "Delete session"}
                    >
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                        <path d="M10 11v6" />
                        <path d="M14 11v6" />
                        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                      </svg>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-4 space-y-3">
        <div className="surface-card-soft rounded-[24px] p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--accent-primary)] text-sm font-semibold text-white">
              {userEmail.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                {userEmail}
              </p>
              <p className="mt-2 text-xs text-[var(--text-secondary)]">
                Your saved chats and profile stay linked to this account.
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => {
              setIsSidebarOpen(false);
              router.push("/profile");
            }}
            className="secondary-button px-4 py-3 text-sm"
          >
            Profile
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="secondary-button px-4 py-3 text-sm"
          >
            Log out
          </button>
        </div>
      </div>
    </div>
  );

  if (checkingAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="surface-card flex w-full max-w-sm flex-col items-center gap-4 rounded-[30px] p-10 text-center">
          <div className="h-10 w-10 rounded-full border-2 border-[var(--accent-primary)] border-t-transparent animate-spin" />
          <div>
            <p className="text-base font-semibold text-[var(--text-primary)]">
              Preparing your workspace
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Checking your account and loading saved conversations.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
          <div className="relative h-screen overflow-hidden px-4 py-4 md:px-5 md:py-5">
            <div className="page-orb left-[-4rem] top-10 h-40 w-40 bg-[rgba(210,136,66,0.16)]" />
            <div
              className="page-orb right-[-2rem] top-24 h-56 w-56 bg-[rgba(0,123,229,0.12)]"
              style={{ animationDelay: "1.5s" }}
            />
            <div
              className="page-orb bottom-8 left-1/3 h-32 w-32 bg-[rgba(255,255,255,0.75)]"
              style={{ animationDelay: "3s" }}
            />

            <div
              className={`fixed inset-0 z-30 bg-[#1f2a30]/18 backdrop-blur-sm transition-opacity md:hidden ${isSidebarOpen ? "opacity-100" : "pointer-events-none opacity-0"
                }`}
              onClick={closeSidebar}
            />

            <div className="relative flex h-full min-h-0 gap-5 overflow-hidden">
              <aside
                className={`fixed inset-y-4 left-4 z-40 w-[86vw] max-w-[320px] transition-transform duration-300 md:hidden ${isSidebarOpen ? "translate-x-0" : "-translate-x-[120%]"
                  }`}
              >
                {sidebarContent}
              </aside>

              <aside
                className={`hidden h-full flex-shrink-0 overflow-hidden transition-[width] duration-300 md:block ${isDesktopSidebarOpen ? "md:w-[320px]" : "md:w-0"
                  }`}
              >
                <div
                  className={`h-full transition-opacity duration-200 ${isDesktopSidebarOpen ? "opacity-100" : "pointer-events-none opacity-0"
                    }`}
                >
                  {sidebarContent}
                </div>
              </aside>

              <div className="min-w-0 min-h-0 flex-1">
                <div className="surface-card flex h-full min-h-0 flex-col overflow-hidden">
                  <header className="shrink-0 border-b border-[var(--border-subtle)] px-4 py-4 md:px-6">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => {
                            if (window.innerWidth >= 768) {
                              setIsDesktopSidebarOpen((prev) => !prev);
                              return;
                            }

                            setIsSidebarOpen(true);
                          }}
                          className="secondary-button h-11 w-11 p-0"
                          aria-label="Toggle sidebar"
                        >
                          <svg
                            width="20"
                            height="20"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <line x1="3" y1="12" x2="21" y2="12" />
                            <line x1="3" y1="6" x2="21" y2="6" />
                            <line x1="3" y1="18" x2="21" y2="18" />
                          </svg>
                        </button>
                        <div>
                          <h2 className="text-2xl font-semibold text-[var(--text-primary)]">
                            Chat
                          </h2>
                        </div>
                      </div>
                    </div>
                  </header>

                  <main
                    className={`min-h-0 flex-1 px-4 pb-4 pt-5 md:px-6 ${messages.length === 0 ? "overflow-hidden" : "overflow-y-auto"
                      }`}
                  >
                    {messages.length === 0 ? (
                      <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center py-4 text-center">
                        <h3 className="text-3xl font-semibold text-[var(--text-primary)] md:text-4xl">
                          Start a new conversation
                        </h3>
                        <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-secondary)] md:text-base">
                          Ask about insurance plans, regulations, waiting periods, or
                          policy eligibility.
                        </p>

                        <div className="mt-8 w-full">
                          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                            {SUGGESTIONS.map((suggestion, index) => (
                              <button
                                key={index}
                                type="button"
                                onClick={() => sendMessage(suggestion)}
                                className="surface-card-strong rounded-[24px] p-5 text-left transition-transform hover:-translate-y-0.5"
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <p className="text-[15px] leading-7 text-[var(--text-primary)]">
                                    {suggestion}
                                  </p>
                                  <span className="mt-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--accent-primary)]">
                                    Start
                                  </span>
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 pb-6">
                        {messages.map((msg) => (
                          <div
                            key={msg.id}
                            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"
                              }`}
                          >
                            <div
                              className={`max-w-[92%] md:max-w-[84%] ${msg.role === "assistant" ? "w-full" : ""
                                }`}
                            >
                              {msg.role === "assistant" && (
                                <div className="mb-2 flex items-center gap-3 px-1">
                                  <div>
                                    <p className="text-xs text-[var(--text-secondary)]">
                                      {formatMessageTime(msg.timestamp)}
                                    </p>
                                  </div>
                                </div>
                              )}

                              <div
                                className={`rounded-[28px] border px-5 py-4 shadow-sm md:px-6 ${msg.role === "user"
                                    ? "border-transparent bg-[var(--accent-primary)] text-white"
                                    : "border-[var(--border-subtle)] bg-white/92"
                                  }`}
                              >
                                {msg.role === "user" ? (
                                  <div>
                                    <p className="text-[15px] leading-7 md:text-[15.5px]">
                                      {msg.content}
                                    </p>
                                    <p className="mt-3 text-right text-xs text-white/72">
                                      {formatMessageTime(msg.timestamp)}
                                    </p>
                                  </div>
                                ) : (
                                  <div className="markdown-body text-[15px] leading-7 md:text-[15.5px]">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                      {msg.content}
                                    </ReactMarkdown>
                                  </div>
                                )}
                              </div>

                              {msg.role === "assistant" &&
                                msg.sources &&
                                msg.sources.length > 0 && (
                                  <div className="mt-4 flex flex-wrap gap-2 px-1">
                                    {msg.sources.map((src, sourceIndex) => (
                                      <div
                                        key={`${src.document_title}-${sourceIndex}`}
                                        className="inline-flex max-w-full items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-xs text-[var(--text-secondary)]"
                                        title={src.chunk_preview}
                                      >
                                        <span className="truncate font-semibold text-[var(--text-primary)]">
                                          {src.document_title}
                                        </span>
                                        {src.page_number !== null && (
                                          <span className="text-[var(--accent-primary)]">
                                            page {src.page_number}
                                          </span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                            </div>
                          </div>
                        ))}

                        {isLoading && (
                          <div className="flex justify-start">
                            <div className="w-full max-w-[92%] md:max-w-[84%]">
                              <div className="mb-2 flex items-center gap-3 px-1">
                                <div>
                                  <p className="text-xs text-[var(--text-secondary)]">
                                    Thinking through your question
                                  </p>
                                </div>
                              </div>
                              <div className="inline-flex items-center gap-2 rounded-[26px] border border-[var(--border-subtle)] bg-white/92 px-5 py-4">
                                <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--accent-primary)]" />
                                <span
                                  className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--accent-primary)]"
                                  style={{ animationDelay: "120ms" }}
                                />
                                <span
                                  className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--accent-primary)]"
                                  style={{ animationDelay: "240ms" }}
                                />
                              </div>
                            </div>
                          </div>
                        )}

                        <div ref={messagesEndRef} className="h-2" />
                      </div>
                    )}
                  </main>

                  <div className="shrink-0 border-t border-[var(--border-subtle)] bg-white/60 px-4 py-4 md:px-6 md:py-5">
                    <div className="mx-auto max-w-4xl">
                      <form onSubmit={handleSubmit}>
                        <div className="surface-card-soft flex items-end gap-3 rounded-[28px] p-3">
                          <textarea
                            ref={inputRef}
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Ask about policy eligibility, regulations, waiting periods, or plan types..."
                            rows={1}
                            className="min-h-[56px] w-full resize-none bg-transparent px-2 py-3 text-[15px] leading-7 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
                          />
                          <button
                            type="submit"
                            disabled={!input.trim() || isLoading}
                            className="primary-button h-12 w-12 rounded-full p-0"
                            aria-label="Send message"
                          >
                            <svg
                              width="18"
                              height="18"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2.4"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
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
                </div>
              </div>
            </div>
          </div>
          );
}
