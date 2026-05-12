"use client";

import Lottie from "lottie-react";
import loaderAnimation from "../../public/t5d42NEZJZ.json";

interface LottieLoaderProps {
  /** Width/height in pixels — defaults to 120 */
  size?: number;
  /** Optional message shown below the animation */
  message?: string;
  /** Optional sub-message (lighter text) */
  subMessage?: string;
  /** If true, renders full-screen centered. Otherwise inline. */
  fullScreen?: boolean;
}

export default function LottieLoader({
  size = 120,
  message,
  subMessage,
  fullScreen = false,
}: LottieLoaderProps) {
  const content = (
    <div className="flex flex-col items-center gap-3">
      <div style={{ width: size, height: size }}>
        <Lottie animationData={loaderAnimation} loop className="w-full h-full" />
      </div>
      {message && (
        <p className="text-base font-semibold text-[var(--text-primary)] text-center">
          {message}
        </p>
      )}
      {subMessage && (
        <p className="mt-0.5 text-sm text-[var(--text-secondary)] text-center max-w-xs">
          {subMessage}
        </p>
      )}
    </div>
  );

  if (fullScreen) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        {content}
      </div>
    );
  }

  return content;
}
