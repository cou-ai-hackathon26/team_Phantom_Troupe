"use client";

import { LoaderCircle, Mic, Square } from "lucide-react";
import type { MicState } from "@/hooks/use-speech-input";
import { cn } from "@/lib/utils";

interface MicButtonProps {
  state: MicState;
  onStart: () => void;
  onStop: () => void;
  disabled?: boolean;
}

export function MicButton({ state, onStart, onStop, disabled }: MicButtonProps) {
  const active = state === "listening" || state === "recording";
  const busy = state === "transcribing";
  return (
    <button
      type="button"
      onClick={active ? onStop : onStart}
      disabled={disabled || busy}
      aria-pressed={active}
      aria-label={active ? "শোনা বন্ধ করুন" : busy ? "কথা লেখায় রূপান্তর হচ্ছে" : "মাইকে প্রশ্ন বলুন"}
      className={cn(
        "relative flex size-14 shrink-0 items-center justify-center rounded-full text-primary-foreground transition-colors sm:size-16",
        active ? "bg-destructive" : "bg-primary hover:bg-primary/90",
        "disabled:opacity-60",
      )}
    >
      {active && (
        <span
          className="absolute inset-0 animate-ping rounded-full bg-destructive/40 motion-reduce:animate-none"
          aria-hidden
        />
      )}
      {busy ? (
        <LoaderCircle className="size-6 animate-spin motion-reduce:animate-none" aria-hidden />
      ) : active ? (
        <Square className="relative size-5 fill-current" aria-hidden />
      ) : (
        <Mic className="size-6" aria-hidden />
      )}
    </button>
  );
}
