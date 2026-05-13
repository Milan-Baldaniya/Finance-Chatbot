"use client";

import { memo, useEffect, useRef, useState, type CSSProperties } from "react";

const STAGES = [
  { text: "Understanding your question", icon: "\u{1F4AD}", duration: 2500 },
  { text: "Searching knowledge base", icon: "\u{1F50D}", duration: 3500 },
  { text: "Analyzing relevant documents", icon: "\u{1F4C4}", duration: 4000 },
  { text: "Preparing your answer", icon: "\u{270D}\u{FE0F}", duration: 0 },
];

function ThinkingIndicator() {
  const [stage, setStage] = useState(0);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    let elapsed = 0;
    timersRef.current = [];

    for (let i = 1; i < STAGES.length; i++) {
      const prevDuration = STAGES[i - 1].duration;
      if (prevDuration === 0) break;

      elapsed += prevDuration;
      timersRef.current.push(setTimeout(() => setStage(i), elapsed));
    }

    return () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
    };
  }, []);

  const current = STAGES[stage];
  const progressDuration = current.duration ? Math.max(current.duration - 180, 900) : 1800;

  return (
    <div className="opacity-100 translate-y-0 transition-all duration-300 ease-out">
      <div className="mx-auto w-full max-w-4xl">
        <div className="inline-block">
          <div className="flex items-center gap-3">
            <span
              key={stage}
              className="animate-slide-in inline-flex items-baseline gap-1.5 text-[13.5px] text-[var(--text-secondary)]"
            >
              <span className="loading-stage-icon leading-none">{current.icon}</span>
              <span>{current.text}</span>
              <span className="relative top-[-1px] inline-flex items-center gap-[3px]">
                {[0, 1, 2].map((dot) => (
                  <span
                    key={dot}
                    className="loading-dot inline-block h-[4px] w-[4px] rounded-full"
                    style={
                      {
                        "--dot-delay": `${dot * 140}ms`,
                        "--dot-opacity": `${0.38 + dot * 0.1}`,
                      } as CSSProperties
                    }
                  />
                ))}
              </span>
            </span>
          </div>

          <div className="mt-3 grid w-full grid-cols-4 gap-1.5">
            {STAGES.map((_, i) => (
              <div
                key={i}
                className="loading-progress-segment relative h-[6px] overflow-hidden rounded-full transition-all duration-500 ease-out"
                style={{ "--segment-index": i } as CSSProperties}
              >
                <span
                  className={`absolute inset-y-0 left-0 rounded-full ${
                    i < stage
                      ? "w-full loading-progress-complete"
                      : i === stage
                        ? "loading-progress-fill"
                        : "w-0"
                  }`}
                  style={
                    i === stage
                      ? ({ "--loading-fill-duration": `${progressDuration}ms` } as CSSProperties)
                      : undefined
                  }
                />
                {i === stage && (
                  <>
                    <span
                      className="loading-progress-head absolute inset-y-0 left-0 w-[5px] rounded-full"
                      style={{ "--loading-fill-duration": `${progressDuration}ms` } as CSSProperties}
                    />
                    <span className="loading-progress-shine absolute inset-y-0 w-3 rounded-full" />
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default memo(ThinkingIndicator);
