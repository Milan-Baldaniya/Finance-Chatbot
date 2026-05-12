"use client";

import { memo, useEffect, useRef, useState } from "react";
import Lottie from "lottie-react";
import loaderAnimation from "../../public/t5d42NEZJZ.json";

const STAGES = [
  { text: "Understanding your question", icon: "💭", duration: 2500 },
  { text: "Searching knowledge base",    icon: "🔍", duration: 3500 },
  { text: "Analyzing relevant documents", icon: "📄", duration: 4000 },
  { text: "Preparing your answer",        icon: "✍️", duration: 0 },  // 0 = stays forever
];

function ThinkingIndicator() {
  const [stage, setStage] = useState(0);
  const [exiting, setExiting] = useState(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    let elapsed = 0;

    for (let i = 1; i < STAGES.length; i++) {
      const prevDuration = STAGES[i - 1].duration;
      if (prevDuration === 0) break; // last stage has no timer — it stays
      elapsed += prevDuration;
      timersRef.current.push(setTimeout(() => setStage(i), elapsed));
    }

    return () => timersRef.current.forEach(clearTimeout);
  }, []);

  const current = STAGES[stage];

  return (
    <div
      className={`transition-all duration-300 ease-out ${
        exiting ? "opacity-0 translate-y-[-4px]" : "opacity-100 translate-y-0"
      }`}
    >
      <div className="mx-auto w-full max-w-4xl">
        {/* FinBot avatar + label */}
        <div className="mb-2.5 flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--accent-primary)]">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a5 5 0 0 1 5 5v2a5 5 0 0 1-10 0V7a5 5 0 0 1 5-5Z" />
              <path d="M2 17c0-2.8 2.2-5 5-5h10c2.8 0 5 2.2 5 5v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1Z" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-[var(--text-primary)]">FinBot</span>
        </div>

        {/* Status row */}
        <div className="pl-9">
          <div className="flex items-center gap-3">
            {/* Lottie loader replacing old CSS spinner */}
            <div className="relative shrink-0" style={{ width: 36, height: 36 }}>
              <Lottie animationData={loaderAnimation} loop className="w-full h-full" />
            </div>

            {/* Stage text + trailing dots — all on the same baseline */}
            <span
              key={stage}
              className="animate-slide-in inline-flex items-baseline gap-1.5 text-[13.5px] text-[var(--text-secondary)]"
            >
              <span className="leading-none">{current.icon}</span>
              <span>{current.text}</span>
              <span className="relative top-[-1px] inline-flex items-center gap-[3px]">
                <span className="inline-block h-[4px] w-[4px] rounded-full bg-[var(--text-muted)] animate-pulse" />
                <span className="inline-block h-[4px] w-[4px] rounded-full bg-[var(--text-muted)] animate-pulse" style={{ animationDelay: "200ms" }} />
                <span className="inline-block h-[4px] w-[4px] rounded-full bg-[var(--text-muted)] animate-pulse" style={{ animationDelay: "400ms" }} />
              </span>
            </span>
          </div>

          {/* Progress bar */}
          <div className="mt-3 flex items-center gap-1.5">
            {STAGES.map((_, i) => (
              <div
                key={i}
                className={`h-[3px] rounded-full transition-all duration-500 ease-out ${
                  i <= stage
                    ? "w-8 bg-[var(--accent-primary)]"
                    : "w-4 bg-[var(--border-subtle)]"
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default memo(ThinkingIndicator);
