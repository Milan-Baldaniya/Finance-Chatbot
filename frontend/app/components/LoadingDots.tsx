"use client";

import { memo, useEffect, useRef, useState } from "react";

const STAGES = [
  { text: "Understanding your question", icon: "💭", duration: 2500 },
  { text: "Searching knowledge base",    icon: "🔍", duration: 3500 },
  { text: "Analyzing relevant documents", icon: "📄", duration: 4000 },
  { text: "Preparing your answer",        icon: "✍️", duration: 0 },
];

function ThinkingIndicator() {
  const [stage, setStage] = useState(0);
  const [mounted, setMounted] = useState(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    requestAnimationFrame(() => setMounted(true));

    let elapsed = 0;
    for (let i = 1; i < STAGES.length; i++) {
      const prevDuration = STAGES[i - 1].duration;
      if (prevDuration === 0) break;
      elapsed += prevDuration;
      timersRef.current.push(setTimeout(() => setStage(i), elapsed));
    }
    return () => timersRef.current.forEach(clearTimeout);
  }, []);

  const progress = ((stage + 1) / STAGES.length) * 100;

  return (
    <div
      className={`mx-auto w-full max-w-4xl transition-all duration-400 ease-out ${
        mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
      }`}
    >
      {/* Compact inline card */}
      <div className="thinking-card">
        {/* Animated gradient border */}
        <div className="thinking-border" />

        <div className="thinking-inner">
          {/* Left: stage icon with pulse ring */}
          <div className="thinking-icon-wrap">
            <div className="thinking-icon-ring" />
            <span className="thinking-icon-emoji">{STAGES[stage].icon}</span>
          </div>

          {/* Center: text + progress */}
          <div className="thinking-content">
            {/* Crossfade text */}
            <div className="thinking-text-track">
              {STAGES.map((s, i) => (
                <span
                  key={i}
                  className="thinking-text-item"
                  data-active={i === stage}
                  style={{
                    transform: `translateY(${i === stage ? "0" : i < stage ? "-110%" : "110%"})`,
                    opacity: i === stage ? 1 : 0,
                  }}
                >
                  {s.text}
                </span>
              ))}
            </div>

            {/* Progress rail */}
            <div className="thinking-rail">
              {/* Filled portion */}
              <div className="thinking-fill" style={{ width: `${progress}%` }}>
                <div className="thinking-fill-shimmer" />
              </div>

              {/* Step dots on the rail */}
              {STAGES.map((_, i) => (
                <div
                  key={i}
                  className="thinking-step-dot"
                  data-reached={i <= stage}
                  style={{ left: `${((i + 0.5) / STAGES.length) * 100}%` }}
                />
              ))}
            </div>
          </div>

          {/* Right: bouncing dots */}
          <div className="thinking-dots">
            <span className="thinking-dot" style={{ animationDelay: "0ms" }} />
            <span className="thinking-dot" style={{ animationDelay: "150ms" }} />
            <span className="thinking-dot" style={{ animationDelay: "300ms" }} />
          </div>
        </div>
      </div>

      <style jsx>{`
        .thinking-card {
          position: relative;
          border-radius: 14px;
          padding: 1.5px;
          background: linear-gradient(
            135deg,
            var(--accent-primary),
            rgba(99, 145, 255, 0.5),
            rgba(180, 200, 255, 0.3),
            var(--accent-primary)
          );
          background-size: 300% 300%;
          animation: borderGlow 4s ease infinite;
        }

        .thinking-inner {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 14px;
          border-radius: 12.5px;
          background: linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.95) 0%,
            rgba(248, 250, 255, 0.97) 100%
          );
          backdrop-filter: blur(8px);
        }

        /* ── Icon ── */
        .thinking-icon-wrap {
          position: relative;
          flex-shrink: 0;
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .thinking-icon-ring {
          position: absolute;
          inset: 0;
          border-radius: 50%;
          border: 1.5px solid var(--accent-primary);
          opacity: 0.3;
          animation: ringPulse 2s ease-in-out infinite;
        }

        .thinking-icon-emoji {
          position: relative;
          font-size: 15px;
          line-height: 1;
          animation: iconPop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) both;
        }

        /* ── Text ── */
        .thinking-content {
          flex: 1;
          min-width: 0;
        }

        .thinking-text-track {
          position: relative;
          height: 18px;
          overflow: hidden;
          margin-bottom: 7px;
        }

        .thinking-text-item {
          position: absolute;
          left: 0;
          top: 0;
          white-space: nowrap;
          font-size: 12.5px;
          font-weight: 600;
          letter-spacing: 0.01em;
          color: var(--text-primary);
          transition: all 0.45s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* ── Progress rail ── */
        .thinking-rail {
          position: relative;
          height: 3px;
          border-radius: 3px;
          background: var(--border-subtle);
          overflow: visible;
        }

        .thinking-fill {
          position: absolute;
          top: 0;
          left: 0;
          height: 100%;
          border-radius: 3px;
          overflow: hidden;
          transition: width 0.7s cubic-bezier(0.4, 0, 0.2, 1);
          background: linear-gradient(
            90deg,
            var(--accent-primary) 0%,
            rgba(99, 145, 255, 0.85) 100%
          );
        }

        .thinking-fill-shimmer {
          position: absolute;
          inset: 0;
          background: linear-gradient(
            90deg,
            transparent 0%,
            rgba(255, 255, 255, 0.55) 50%,
            transparent 100%
          );
          animation: shimmerSlide 1.2s ease-in-out infinite;
        }

        /* Step dots */
        .thinking-step-dot {
          position: absolute;
          top: 50%;
          width: 7px;
          height: 7px;
          border-radius: 50%;
          transform: translate(-50%, -50%) scale(0.7);
          background: var(--border-subtle);
          border: 1.5px solid rgba(255, 255, 255, 0.9);
          transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
          z-index: 2;
        }

        .thinking-step-dot[data-reached="true"] {
          background: var(--accent-primary);
          transform: translate(-50%, -50%) scale(1);
          box-shadow: 0 0 6px rgba(var(--accent-primary-rgb, 0, 123, 229), 0.45);
        }

        /* ── Trailing dots ── */
        .thinking-dots {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          gap: 3px;
          padding-left: 2px;
        }

        .thinking-dot {
          display: block;
          width: 4px;
          height: 4px;
          border-radius: 50%;
          background: var(--accent-primary);
          animation: dotWave 1.4s ease-in-out infinite;
        }

        /* ─── Keyframes ─── */
        @keyframes borderGlow {
          0%,
          100% {
            background-position: 0% 50%;
          }
          50% {
            background-position: 100% 50%;
          }
        }

        @keyframes ringPulse {
          0%,
          100% {
            transform: scale(1);
            opacity: 0.25;
          }
          50% {
            transform: scale(1.25);
            opacity: 0.5;
          }
        }

        @keyframes iconPop {
          0% {
            transform: scale(0.5);
            opacity: 0;
          }
          100% {
            transform: scale(1);
            opacity: 1;
          }
        }

        @keyframes shimmerSlide {
          0% {
            transform: translateX(-100%);
          }
          100% {
            transform: translateX(100%);
          }
        }

        @keyframes dotWave {
          0%,
          80%,
          100% {
            transform: translateY(0);
            opacity: 0.35;
          }
          40% {
            transform: translateY(-4px);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}

export default memo(ThinkingIndicator);
