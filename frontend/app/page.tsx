"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// ── Types ──
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// ── Suggested Questions ──
const SUGGESTIONS = [
  "What compliances are required before buying term insurance?",
  "What is the role of IRDAI?",
  "Explain KYC and underwriting.",
  "Can I buy insurance for my dependents?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Check backend health and load sessions on mount
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.json())
      .then(() => setIsConnected(true))
      .catch(() => setIsConnected(false));
      
    fetchSessions();
  }, []);

  const fetchSessions = () => {
    try {
      const stored = localStorage.getItem("my_finbot_sessions");
      if (stored) {
        setSessions(JSON.parse(stored));
      } else {
        setSessions([]);
      }
    } catch (error) {
      console.error("Failed to load sessions from local storage", error);
    }
  };

  const loadSession = async (sid: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/${sid}`);
      if (res.ok) {
        const data = await res.json();
        const loadedMessages: Message[] = data.map((msg: any) => ({
          id: msg.id || crypto.randomUUID(),
          role: msg.role,
          content: msg.content,
          timestamp: new Date(msg.created_at),
          sources: [] // We don't store sources in db currently to keep it simple, but we could in future
        }));
        setMessages(loadedMessages);
        setSessionId(sid);
      }
    } catch (error) {
      console.error("Failed to load session history", error);
    }
  };

  const createNewChat = () => {
    setMessages([]);
    setSessionId(null);
    fetchSessions(); // Refresh list just in case
  };

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const sendMessage = async (text?: string) => {
    const question = (text || input).trim();
    if (!question || isLoading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });
      const data = await res.json();

      if (!sessionId) {
        setSessionId(data.session_id);
        
        // Save the new session to localStorage
        try {
          const stored = localStorage.getItem("my_finbot_sessions");
          const mySessions = stored ? JSON.parse(stored) : [];
          
          // Only add if it doesn't already exist
          if (!mySessions.some((s: Session) => s.session_id === data.session_id)) {
            const newSession: Session = {
              session_id: data.session_id,
              title: question.substring(0, 30) + (question.length > 30 ? "..." : ""),
              created_at: data.created_at || new Date().toISOString()
            };
            const updatedSessions = [newSession, ...mySessions];
            localStorage.setItem("my_finbot_sessions", JSON.stringify(updatedSessions));
            setSessions(updatedSessions);
          }
        } catch (e) {
          console.error("Error saving to localStorage", e);
        }
      }

      const botMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        timestamp: new Date(data.created_at),
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch {
      const errMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Sorry, I couldn't reach the server. Please ensure the backend is running on port 8000.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#212121] text-[#ECECEC] font-sans overflow-hidden">
      {/* ── Custom CSS for Markdown ── */}
      <style dangerouslySetInnerHTML={{__html: `
        .markdown-body p { margin-bottom: 1em; line-height: 1.6; }
        .markdown-body ul { list-style-type: disc; margin-left: 1.5em; margin-bottom: 1em; }
        .markdown-body ol { list-style-type: decimal; margin-left: 1.5em; margin-bottom: 1em; }
        .markdown-body li { margin-bottom: 0.5em; line-height: 1.6; }
        .markdown-body strong { font-weight: 600; color: #FFFFFF; }
        .markdown-body code { background: #2f2f2f; padding: 0.2em 0.4em; border-radius: 4px; font-size: 0.9em; font-family: monospace; }
        .markdown-body pre { background: #1a1a1a; padding: 1em; border-radius: 8px; overflow-x: auto; margin-bottom: 1em; border: 1px solid #333; }
        .markdown-body pre code { background: transparent; padding: 0; }
        .markdown-body h1, .markdown-body h2, .markdown-body h3 { font-weight: 600; margin-top: 1.5em; margin-bottom: 0.5em; color: #FFFFFF; }
        .markdown-body a { color: #58a6ff; text-decoration: none; }
        .markdown-body a:hover { text-decoration: underline; }
      `}} />

      {/* ── Sidebar ── */}
      <div 
        className={`${isSidebarOpen ? "w-[260px]" : "w-0"} flex-shrink-0 transition-all duration-300 bg-[#171717] flex flex-col border-r border-[#333] hidden md:flex`}
        style={{ overflow: "hidden" }}
      >
        <div className="p-3">
          <button 
            onClick={createNewChat}
            className="flex items-center gap-2 w-full hover:bg-[#2f2f2f] transition-colors p-2.5 rounded-md text-sm font-medium text-gray-200"
          >
            <div className="w-6 h-6 rounded-full bg-white text-black flex items-center justify-center font-bold text-lg leading-none pb-[2px]">
              +
            </div>
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <div className="text-xs text-gray-500 font-semibold mb-3 px-2 mt-2">Previous Chats</div>
          
          {sessions.length === 0 ? (
             <div className="text-xs text-gray-600 px-2 italic">No previous chats</div>
          ) : (
            <div className="space-y-1">
              {sessions.map(session => (
                <div 
                  key={session.session_id}
                  onClick={() => loadSession(session.session_id)}
                  className={`text-sm text-gray-300 truncate cursor-pointer p-2 rounded-md transition ${sessionId === session.session_id ? 'bg-[#2f2f2f] font-medium' : 'hover:bg-[#2f2f2f]'}`}
                  title={session.title}
                >
                  {session.title}
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Connection Status */}
        <div className="p-4 border-t border-[#333] text-sm flex items-center justify-between">
           <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-semibold">
                U
              </div>
              <span className="font-medium text-gray-200">Admin</span>
           </div>
           <div title={isConnected ? "API Connected" : "API Offline"} className={`w-2.5 h-2.5 rounded-full shadow-[0_0_8px_rgba(0,0,0,0.5)] ${isConnected ? "bg-green-500 shadow-green-500/50" : "bg-red-500 shadow-red-500/50"}`}></div>
        </div>
      </div>

      {/* ── Main Chat Area ── */}
      <div className="flex-1 flex flex-col h-full relative">
        {/* Mobile Header */}
        <div className="h-12 flex items-center px-4 border-b border-[#333] md:hidden text-gray-300 bg-[#212121]">
           <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 -ml-2 hover:bg-[#2f2f2f] rounded-md transition">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
           </button>
           <span className="ml-2 font-medium text-white">FinBot</span>
        </div>

        <main className="flex-1 overflow-y-auto scroll-smooth w-full">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center px-4 pb-32">
              <div className="w-16 h-16 bg-white text-black rounded-full flex items-center justify-center text-2xl font-bold mb-6 shadow-lg shadow-white/10">
                F
              </div>
              <h2 className="text-2xl font-semibold mb-10 text-white tracking-tight">How can I help you today?</h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(s)}
                    className="p-4 border border-[#444] rounded-xl text-left hover:bg-[#2f2f2f] hover:border-gray-500 transition-all text-[14px] text-gray-300 leading-relaxed shadow-sm"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center py-6 pb-40 w-full">
              {messages.map((msg, idx) => (
                <div key={msg.id} className="w-full flex justify-center py-4 px-4 sm:px-6">
                  <div className={`w-full max-w-3xl flex gap-4 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    
                    {/* Assistant Avatar */}
                    {msg.role === "assistant" && (
                      <div className="w-8 h-8 mt-1 rounded-full bg-white flex-shrink-0 flex items-center justify-center text-black font-bold text-sm shadow-sm border border-gray-200">
                        F
                      </div>
                    )}

                    {/* Content */}
                    <div className={`flex flex-col gap-1.5 ${msg.role === "user" ? "items-end max-w-[80%]" : "w-full max-w-[90%]"}`}>
                      {msg.role === "user" ? (
                        <div className="bg-[#2f2f2f] px-5 py-3 rounded-2xl rounded-tr-sm text-gray-100 text-[15.5px] leading-relaxed shadow-sm">
                          {msg.content}
                        </div>
                      ) : (
                        <div className="text-gray-100 text-[15.5px] w-full pt-1">
                          <div className="markdown-body text-gray-200">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        </div>
                      )}

                      {/* Sources (Citations) */}
                      {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {msg.sources.map((src, si) => (
                            <div
                              key={si}
                              className="px-3 py-1.5 rounded-full bg-[#1a1a1a] border border-[#333] hover:border-[#555] text-xs text-gray-400 flex items-center gap-1.5 cursor-pointer transition-colors"
                            >
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8l-6 6v12a2 2 0 0 0 2 2z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                              <span className="truncate max-w-[180px] font-medium text-gray-300">{src.document_title}</span>
                              {src.page_number !== null && <span className="text-gray-500 ml-1">pg {src.page_number}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              
              {isLoading && (
                 <div className="w-full flex justify-center py-4 px-4 sm:px-6">
                  <div className="w-full max-w-3xl flex gap-4 justify-start">
                    <div className="w-8 h-8 mt-1 rounded-full bg-white flex-shrink-0 flex items-center justify-center text-black font-bold text-sm shadow-sm border border-gray-200">
                      F
                    </div>
                    <div className="flex gap-1.5 items-center mt-3 ml-2">
                      <div className="w-2 h-2 rounded-full bg-gray-500 animate-pulse" />
                      <div className="w-2 h-2 rounded-full bg-gray-500 animate-pulse" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 rounded-full bg-gray-500 animate-pulse" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                 </div>
              )}
              
              <div ref={messagesEndRef} className="h-10" />
            </div>
          )}
        </main>

        {/* ── Input Area ── */}
        <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-[#212121] via-[#212121] to-transparent pt-10 pb-6 px-4">
          <div className="max-w-3xl mx-auto relative">
            <form onSubmit={handleSubmit} className="relative flex items-end">
              <div className="w-full bg-[#2f2f2f] rounded-3xl shadow-lg border border-[#444] flex items-end pl-5 pr-2 py-2 focus-within:ring-1 focus-within:ring-[#555] transition-all">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Message FinBot..."
                  rows={1}
                  className="w-full bg-transparent text-[#ECECEC] placeholder-gray-400 border-none outline-none resize-none py-2.5 max-h-[200px] overflow-y-auto text-[15.5px] leading-relaxed"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className={`mb-1 ml-2 p-2.5 rounded-full flex-shrink-0 transition-all ${
                    input.trim() && !isLoading 
                      ? "bg-white text-black hover:bg-gray-200 cursor-pointer shadow-md" 
                      : "bg-[#444] text-gray-500 cursor-not-allowed"
                  }`}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="19" x2="12" y2="5"></line>
                    <polyline points="5 12 12 5 19 12"></polyline>
                  </svg>
                </button>
              </div>
            </form>
            <div className="text-center text-xs text-gray-500 mt-3 font-medium">
              FinBot can make mistakes. Consider verifying important compliance information.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
