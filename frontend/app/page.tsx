"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/utils/supabase/client";

import ChatSidebar from "./components/ChatSidebar";
import MessageBubble, { type Message } from "./components/MessageBubble";
import ChatInput from "./components/ChatInput";
import WelcomeScreen from "./components/WelcomeScreen";
import ThinkingIndicator from "./components/LoadingDots";
import LottieLoader from "./components/LottieLoader";

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

function normalizeSessions(raw: Session[]): Session[] {
  const byId = new Map<string, Session>();
  raw.forEach((s) => { if (!byId.has(s.session_id)) byId.set(s.session_id, s); });
  const unique = Array.from(byId.values()).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  const deduped: Session[] = [];
  for (const s of unique) {
    const dup = deduped.find(
      (e) =>
        e.title.trim() === s.title.trim() &&
        Math.abs(new Date(e.created_at).getTime() - new Date(s.created_at).getTime()) < 60_000
    );
    if (!dup) deduped.push(s);
  }
  return deduped;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isDesktopSidebarOpen, setIsDesktopSidebarOpen] = useState(true);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState("");
  const [checkingAuth, setCheckingAuth] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const supabaseRef = useRef<ReturnType<typeof createClient> | null>(null);
  const sendLockRef = useRef(false);
  const router = useRouter();

  const getSupabase = useCallback(() => {
    if (!supabaseRef.current) supabaseRef.current = createClient();
    return supabaseRef.current;
  }, []);

  const getAuthToken = useCallback(async (): Promise<string | null> => {
    const { data: { session } } = await getSupabase().auth.getSession();
    return session?.access_token || null;
  }, [getSupabase]);

  const fetchSessions = useCallback(async () => {
    const token = await getAuthToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(normalizeSessions(data));
      }
    } catch (e) {
      console.error("Failed to load sessions", e);
    }
  }, [getAuthToken]);

  const fetchSuggestions = useCallback(async () => {
    setIsLoadingSuggestions(true);
    const token = await getAuthToken();
    if (!token) {
      setIsLoadingSuggestions(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/profile/suggestions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.suggestions)) {
        setSuggestions(data.suggestions.filter((item: unknown) => typeof item === "string" && item.trim()));
      }
    } catch (e) {
      console.error("Failed to load profile suggestions", e);
    } finally {
      setIsLoadingSuggestions(false);
    }
  }, [getAuthToken]);

  // Auth init
  useEffect(() => {
    const init = async () => {
      const { data: { user } } = await getSupabase().auth.getUser();
      if (!user) { router.push("/sign-in"); return; }
      setUserEmail(user.email || "User");
      const token = await getAuthToken();
      if (token) {
        try {
          const res = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            const data = await res.json();
            if (!data.onboarding_completed) { router.push("/onboarding"); return; }
          }
        } catch (e) { console.error("Error checking onboarding:", e); }
      }
      setCheckingAuth(false);
      fetchSessions();
      fetchSuggestions();
    };
    init();
  }, [fetchSessions, fetchSuggestions, getAuthToken, getSupabase, router]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Load session history
  const loadSession = useCallback(async (sid: string) => {
    if (isLoading || deletingSessionId) return;
    // Instant switch — show empty while loading
    setSessionId(sid);
    setMessages([]);
    setIsSidebarOpen(false);

    const token = await getAuthToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/chat/${sid}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data: ChatHistoryMessage[] = await res.json();
      setMessages(
        data.map((m) => ({
          id: m.id || crypto.randomUUID(),
          role: m.role,
          content: m.content,
          timestamp: new Date(m.created_at),
          sources: [],
        }))
      );
    } catch (e) { console.error("Failed to sync session history", e); }
  }, [isLoading, deletingSessionId, getAuthToken]);

  // Delete session — optimistic
  const handleDeleteSession = useCallback(async (sid: string) => {
    if (isLoading || deletingSessionId) return;
    const token = await getAuthToken();
    if (!token) { router.push("/sign-in"); return; }

    // Optimistic: remove from UI immediately
    setDeletingSessionId(sid);
    setSessions((prev) => prev.filter((s) => s.session_id !== sid));
    if (sessionId === sid) { setMessages([]); setSessionId(null); }

    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sid}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        // Revert on failure
        fetchSessions();
      }
    } catch (e) {
      console.error("Failed to delete session", e);
      fetchSessions();
    } finally {
      setDeletingSessionId(null);
    }
  }, [isLoading, deletingSessionId, sessionId, getAuthToken, router, fetchSessions]);

  const createNewChat = useCallback(() => {
    if (isLoading) return;
    setMessages([]);
    setSessionId(null);
    setIsSidebarOpen(false);
  }, [isLoading]);

  // Send message — streaming via SSE
  const sendMessage = useCallback(async (documentContext?: string, documentName?: string, suggestedQuestion?: string) => {
    const question = (suggestedQuestion ?? input).trim();
    if (!question && !documentContext) return;
    
    // The string that the LLM will see — formatted to match backend regex parser
    // Format: [Attached Document: name]\n{full doc text}\n\n{user question}
    let apiQuestion = question;
    if (documentContext && documentName) {
      // documentContext already has "[Attached Document: name]\n{text}\n"
      // We need format: [Attached Document: name]\n{text}\n\n{question}
      const docText = documentContext
        .replace(`[Attached Document: ${documentName}]\n`, "")
        .trim();
      apiQuestion = `[Attached Document: ${documentName}]\n${docText}\n\n${question}`.trim();
    }

    // The string that the user will see in the chat bubble (clean question only — doc shown as card)
    const displayQuestion = question || "";

    if (isLoading || sendLockRef.current) return;
    sendLockRef.current = true;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: displayQuestion,
      timestamp: new Date(),
      attachedDocumentName: documentName,
    };
    const botMsgId = crypto.randomUUID();
    const botMsg: Message = {
      id: botMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg, botMsg]);
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
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question: apiQuestion, session_id: sessionId }),
      });

      if (!res.ok || !res.body) {
        const errorPayload = await res.json().catch(() => null);
        const detail = errorPayload?.detail;
        const message = Array.isArray(detail)
          ? detail.map((item) => item.msg || JSON.stringify(item)).join(" ")
          : detail || "Stream request failed";
        throw new Error(message);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === "token") {
              // Append token to the assistant message in real-time
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === botMsgId
                    ? { ...m, content: m.content + event.content }
                    : m
                )
              );
            } else if (event.type === "done") {
              // Apply metadata (sources, session, timestamp)
              if (!sessionId && event.session_id) setSessionId(event.session_id);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === botMsgId
                    ? {
                        ...m,
                        sources: event.sources || [],
                        timestamp: event.created_at
                          ? new Date(event.created_at)
                          : m.timestamp,
                      }
                    : m
                )
              );
              fetchSessions();
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error && error.message
          ? error.message
          : "I could not reach the backend right now. Please check that the API server is running and try again.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === botMsgId
            ? {
                ...m,
                content:
                  m.content ||
                  errorMessage,
              }
            : m
        )
      );
    } finally {
      sendLockRef.current = false;
      setIsLoading(false);
    }
  }, [input, isLoading, sessionId, getAuthToken, router, fetchSessions]);

  const handleLogout = useCallback(async () => {
    await getSupabase().auth.signOut();
    router.push("/sign-in");
  }, [getSupabase, router]);

  const handleProfile = useCallback(() => {
    setIsSidebarOpen(false);
    router.push("/profile");
  }, [router]);

  // Loading screen
  if (checkingAuth) {
    return (
      <LottieLoader
        fullScreen
        size={220}
        message="Preparing your workspace"
        subMessage="Checking your account and loading saved conversations."
      />
    );
  }

  return (
    <div className="relative h-screen overflow-hidden px-4 py-4 md:px-5 md:py-5">
      {/* Background orbs */}
      <div className="page-orb left-[-4rem] top-10 h-40 w-40 bg-[rgba(210,136,66,0.16)]" />
      <div className="page-orb right-[-2rem] top-24 h-56 w-56 bg-[rgba(0,123,229,0.12)]" style={{ animationDelay: "1.5s" }} />
      <div className="page-orb bottom-8 left-1/3 h-32 w-32 bg-[rgba(255,255,255,0.75)]" style={{ animationDelay: "3s" }} />

      {/* Mobile overlay */}
      <div
        className={`fixed inset-0 z-30 bg-[#1f2a30]/18 backdrop-blur-sm transition-opacity md:hidden ${isSidebarOpen ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={() => setIsSidebarOpen(false)}
      />

      <div className="relative flex h-full min-h-0 gap-5 overflow-hidden">
        {/* Mobile sidebar */}
        <aside className={`fixed inset-y-4 left-4 z-40 w-[86vw] max-w-[320px] transition-transform duration-300 md:hidden ${isSidebarOpen ? "translate-x-0" : "-translate-x-[120%]"}`}>
          <ChatSidebar
            sessions={sessions}
            activeSessionId={sessionId}
            userEmail={userEmail}
            isLoading={isLoading}
            deletingSessionId={deletingSessionId}
            onNewChat={createNewChat}
            onSelectSession={loadSession}
            onDeleteSession={handleDeleteSession}
            onLogout={handleLogout}
            onProfile={handleProfile}
          />
        </aside>

        {/* Desktop sidebar */}
        <aside className={`hidden h-full flex-shrink-0 overflow-hidden transition-[width] duration-300 md:block ${isDesktopSidebarOpen ? "md:w-[320px]" : "md:w-0"}`}>
          <div className={`h-full transition-opacity duration-200 ${isDesktopSidebarOpen ? "opacity-100" : "pointer-events-none opacity-0"}`}>
            <ChatSidebar
              sessions={sessions}
              activeSessionId={sessionId}
              userEmail={userEmail}
              isLoading={isLoading}
              deletingSessionId={deletingSessionId}
              onNewChat={createNewChat}
              onSelectSession={loadSession}
              onDeleteSession={handleDeleteSession}
              onLogout={handleLogout}
              onProfile={handleProfile}
            />
          </div>
        </aside>

        {/* Main chat */}
        <div className="min-w-0 min-h-0 flex-1">
          <div className="surface-card flex h-full min-h-0 flex-col overflow-hidden">
            {/* Header */}
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
                    className="secondary-button h-11 w-11 cursor-pointer p-0"
                    aria-label="Toggle sidebar"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="3" y1="12" x2="21" y2="12" />
                      <line x1="3" y1="6" x2="21" y2="6" />
                      <line x1="3" y1="18" x2="21" y2="18" />
                    </svg>
                  </button>
                  <h2 className="text-2xl font-semibold text-[var(--text-primary)]">Chat</h2>
                </div>
              </div>
            </header>

            {/* Messages */}
            <main className={`min-h-0 flex-1 px-4 pb-4 pt-5 md:px-6 ${messages.length === 0 ? "overflow-hidden" : "overflow-y-auto"}`}>
              {messages.length === 0 ? (
                <WelcomeScreen
                  suggestions={suggestions}
                  isLoadingSuggestions={isLoadingSuggestions}
                  onSend={(question) => sendMessage(undefined, undefined, question)}
                />
              ) : (
                <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 pb-6">
                  {messages.map((msg) => {
                    // Skip the empty bot placeholder entirely — ThinkingIndicator covers that state
                    if (msg.role === "assistant" && msg.content === "") return null;
                    return <MessageBubble key={msg.id} msg={msg} />;
                  })}

                  {/* Show thinking indicator while waiting for first token */}
                  {isLoading && messages.some((m) => m.role === "assistant" && m.content === "") && (
                    <ThinkingIndicator />
                  )}

                  <div ref={messagesEndRef} className="h-2" />
                </div>
              )}
            </main>

            {/* Input */}
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={(docContext, docName) => sendMessage(docContext, docName)}
              isLoading={isLoading}
              getAuthToken={getAuthToken}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
