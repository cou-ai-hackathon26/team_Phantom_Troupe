"use client";

import { LoaderCircle, Square, Volume2 } from "lucide-react";
import { useSpeechOutput } from "@/hooks/use-speech-output";
import { cn } from "@/lib/utils";

interface ListenButtonProps {
  text: string;
  token: string | null;
}

/** 🔊 শুনুন — reads the answer aloud for people who find listening easier than reading. */
export function ListenButton({ text, token }: ListenButtonProps) {
  const { state, error, speak, stop } = useSpeechOutput();
  const active = state !== "idle";

  return (
    <>
      <button
        type="button"
        onClick={() => (active ? stop() : void speak(text, token))}
        aria-pressed={state === "playing"}
        aria-label={active ? "শোনানো বন্ধ করুন" : "উত্তরটি শুনুন"}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-medium transition-colors",
          active ? "bg-primary-soft text-primary" : "text-primary hover:bg-primary-soft",
        )}
      >
        {state === "loading" ? (
          <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
        ) : state === "playing" ? (
          <Square className="size-4 fill-current" aria-hidden />
        ) : (
          <Volume2 className="size-4" aria-hidden />
        )}
        {state === "loading" ? "আসছে…" : state === "playing" ? "থামান" : "শুনুন"}
      </button>
      {error && (
        <span className="basis-full text-sm text-muted-foreground" role="status">
          {error}
        </span>
      )}
    </>
  );
}
