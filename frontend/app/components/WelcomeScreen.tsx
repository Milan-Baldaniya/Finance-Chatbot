"use client";

import { memo } from "react";

const DEFAULT_SUGGESTIONS = [
  "What compliances are required before buying term insurance?",
  "What is the role of IRDAI?",
  "Explain KYC and underwriting.",
  "Can I buy insurance for my dependents?",
];

interface WelcomeScreenProps {
  suggestions?: string[];
  isLoadingSuggestions?: boolean;
  onSend: (text: string) => void;
}

function WelcomeScreen({ suggestions, isLoadingSuggestions = false, onSend }: WelcomeScreenProps) {
  const displaySuggestions = suggestions?.length ? suggestions : DEFAULT_SUGGESTIONS;

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center py-4 text-center">
      <h3 className="text-3xl font-semibold text-[var(--text-primary)] md:text-4xl">
        Start a new conversation
      </h3>
      <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-secondary)] md:text-base">
        Ask about insurance plans, regulations, waiting periods, or policy eligibility.
      </p>

      <div className="mt-8 w-full">
        {isLoadingSuggestions ? (
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
            Personalizing suggestions...
          </p>
        ) : null}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {isLoadingSuggestions && !suggestions?.length
            ? Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="surface-card-strong min-h-[110px] rounded-[24px] p-5"
              >
                <div className="h-4 w-4/5 animate-pulse rounded-full bg-[rgba(95,111,118,0.16)]" />
                <div className="mt-4 h-4 w-2/3 animate-pulse rounded-full bg-[rgba(95,111,118,0.12)]" />
              </div>
            ))
            : displaySuggestions.map((suggestion, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onSend(suggestion)}
              className="surface-card-strong cursor-pointer rounded-[24px] p-5 text-left transition-transform hover:-translate-y-0.5"
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
  );
}

export default memo(WelcomeScreen);
