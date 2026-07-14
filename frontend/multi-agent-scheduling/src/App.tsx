import { useState, useEffect, useRef } from "react";

const API = "https://multi-agent-scheduling.onrender.com/";

interface Msg {
  type: string;
  content: string;
  tool_calls?: { name: string; args: Record<string, unknown> }[];
  name?: string;
}

// All bookable slots — must mirror the backend's SLOTS list (09:00–17:00 hourly)
const ALL_SLOTS = Array.from({ length: 9 }, (_, i) => `${9 + i}:00`);

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true); // Prevents empty state flash
  const bottom = useRef<HTMLDivElement>(null);

  // Load history on mount
  useEffect(() => {
    fetch(`${API}/api/messages`)
      .then((res) => res.json())
      .then((data) => setMessages(data.messages || []))
      .catch(() => {})
      .finally(() => setInitialLoad(false));
  }, []);

  // Smooth scroll to bottom
  useEffect(() => {
    setTimeout(() => {
      bottom.current?.scrollIntoView({ behavior: "smooth" });
    }, 50);
  }, [messages, loading]);

  async function send(e: React.FormEvent, override?: string) {
    e.preventDefault();
    const text = (override ?? input).trim();
    if (!text || loading) return;

    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      setMessages(data.messages);
    } catch {
      setMessages((prev) => [...prev, { type: "ai", content: "Backend connection failed." }]);
    } finally {
      setLoading(false);
    }
  }

  // Lets slot chips / quick actions submit a message without typing
  function sendQuick(text: string) {
    if (loading) return;
    send({ preventDefault: () => {} } as React.FormEvent, text);
  }

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-white font-sans">

      {/* Header */}
      <header className="shrink-0 border-b border-slate-800/50 bg-slate-900/50 backdrop-blur-sm px-6 py-4">
        <div className="max-w-2xl mx-auto flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-sm font-bold">S</div>
          <div>
            <h1 className="text-sm font-semibold text-white">Scheduling Assistant</h1>
            <p className="text-xs text-slate-500">Book appointments seamlessly</p>
          </div>
        </div>
      </header>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-6">
        <div className="max-w-2xl mx-auto space-y-4">

          {/* Show skeleton while loading history */}
          {initialLoad && (
            <div className="flex justify-start animate-pulse">
              <div className="bg-slate-800 rounded-2xl h-16 w-64 rounded-tl-sm"></div>
            </div>
          )}

          {/* Empty State (only shows if NOT loading and NO messages) */}
          {!initialLoad && messages.length === 0 && (
            <div className="flex flex-col items-center justify-center text-center py-24">
              <div className="w-16 h-16 bg-slate-800/80 border border-slate-700/50 rounded-2xl flex items-center justify-center mb-5 text-3xl shadow-lg">
                📅
              </div>
              <h2 className="text-xl font-semibold text-slate-200 mb-2">Book an Appointment</h2>
              <p className="text-sm text-slate-500 max-w-sm">
                Try saying: <em className="text-slate-400">"I want to book tomorrow at 10am"</em>
              </p>
              <p className="text-xs text-slate-600 mt-2">
                (10:00 and 14:00 tomorrow are pre-booked to test negotiation)
              </p>
            </div>
          )}

          {/* Render Messages */}
          {!initialLoad && messages.map((m, i) => (
            <MessageBubble key={i} message={m} onPickSlot={sendQuick} />
          ))}

          {/* Typing Indicator */}
          {loading && (
            <div className="flex justify-start animate-[fadeIn_0.2s_ease-in]">
              <div className="bg-slate-800 border border-slate-700/50 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                <span className="inline-flex gap-1.5">
                  {[0, 150, 300].map((d) => (
                    <span
                      key={d}
                      className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${d}ms` }}
                    />
                  ))}
                </span>
              </div>
            </div>
          )}

          <div ref={bottom} className="h-4" />
        </div>
      </div>

      {/* Input Area */}
      <footer className="shrink-0 border-t border-slate-800/50 bg-slate-900/50 backdrop-blur-sm p-4">
        <form onSubmit={send} className="max-w-2xl mx-auto flex gap-3 bg-slate-800/50 border border-slate-700/50 rounded-2xl px-4 py-2 focus-within:border-blue-500/50 transition-colors">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            placeholder="Type a message..."
            className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none py-1.5 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-30 disabled:hover:bg-blue-600 text-white rounded-xl px-4 py-1.5 text-sm font-medium transition-all duration-200"
          >
            Send
          </button>
        </form>
      </footer>
    </div>
  );
}

// --- Extracted Message Bubble Component ---
function MessageBubble({ message, onPickSlot }: { message: Msg; onPickSlot: (text: string) => void }) {
  const isHuman = message.type === "human";
  const isToolCall = message.type === "ai" && !!message.tool_calls?.length;
  const isToolResult = message.type === "tool";
  const isAiText = message.type === "ai" && message.content;

  if (isToolCall) {
    return (
      <div className="flex justify-center animate-[fadeIn_0.2s_ease-in]">
        <div className="inline-flex items-center gap-2 text-xs text-slate-400 bg-slate-800/40 border border-slate-700/30 rounded-full px-4 py-1.5">
          <span className="h-1.5 w-1.5 bg-amber-400 rounded-full animate-pulse" />
          {(message.tool_calls ?? []).map((t) => t.name).join(", ")}
        </div>
      </div>
    );
  }
  // Availability results get a rich slot grid instead of a plain badge
  if (isToolResult && message.name === "check_availability") {
    return <AvailabilityCard content={message.content} onPickSlot={onPickSlot} />;
  }

  // Tool Result Badge (reserve_slot / send_booking_notification / fallback)
  if (isToolResult) {
    return (
      <div className="flex justify-center animate-[fadeIn_0.2s_ease-in]">
        <div className="max-w-md w-full bg-emerald-500/5 border border-emerald-500/20 rounded-xl px-4 py-2.5 text-xs text-emerald-400 flex items-start gap-2">
          <span className="mt-0.5">✓</span>
          <div className="min-w-0">
            <span className="font-semibold">{message.name}</span>
            <p className="text-emerald-300/70 mt-0.5 whitespace-pre-wrap">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  // Human / AI Text
  if (isAiText || isHuman) {
    return (
      <div className={`flex gap-3 ${isHuman ? "flex-row-reverse" : ""} animate-[fadeIn_0.2s_ease-in]`}>
        {/* Avatar */}
        <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shadow-sm ${
          isHuman ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-300 border border-slate-600"
        }`}>
          {isHuman ? "U" : "AI"}
        </div>

        {/* Bubble */}
        <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
          isHuman
            ? "bg-blue-600 text-white rounded-tr-sm"
            : "bg-slate-800 border border-slate-700/50 text-slate-100 rounded-tl-sm"
        }`}>
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>
      </div>
    );
  }

  return null;
}

// --- Availability Slot Grid ---

function AvailabilityCard({ content, onPickSlot }: { content: string; onPickSlot: (text: string) => void }) {
  const dateMatch = content.match(/(\d{4}-\d{2}-\d{2})/);
  const date = dateMatch?.[1] ?? null;

  const listMatch = content.match(/Available on [^:]+:\s*(.+)/i);
  const freeSlots = listMatch
    ? listMatch[1].split(",").map((s) => s.trim()).filter(Boolean)
    : [];

  const fullyBooked = /all slots.*booked/i.test(content);
  const couldNotParse = !date || (!listMatch && !fullyBooked);

  // Fall back to a plain text badge for errors ("in the past", "cannot parse", etc.)
  if (couldNotParse) {
    return (
      <div className="flex justify-center animate-[fadeIn_0.2s_ease-in]">
        <div className="max-w-md w-full bg-slate-800/40 border border-slate-700/30 rounded-xl px-4 py-2.5 text-xs text-slate-400">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-center animate-[fadeIn_0.2s_ease-in]">
      <div className="max-w-md w-full bg-slate-800/60 border border-slate-700/50 rounded-2xl px-4 py-3.5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-slate-200">
            Availability {date && `· ${formatDate(date)}`}
          </span>
          <span className="text-[11px] text-slate-500">
            {freeSlots.length} open
          </span>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {ALL_SLOTS.map((slot) => {
            const isFree = freeSlots.includes(slot);
            return (
              <button
                key={slot}
                disabled={!isFree}
                onClick={() => date && onPickSlot(`Book ${date} at ${slot}`)}
                className={`text-xs font-medium rounded-lg px-2 py-2 transition-colors ${
                  isFree
                    ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/20 cursor-pointer"
                    : "bg-slate-900/40 border border-slate-700/40 text-slate-600 line-through cursor-not-allowed"
                }`}
              >
                {slot}
              </button>
            );
          })}
        </div>

        {freeSlots.length > 0 && (
          <p className="text-[11px] text-slate-500 mt-3">Tap an open slot to request it.</p>
        )}
      </div>
    </div>
  );
}

function formatDate(iso: string) {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}