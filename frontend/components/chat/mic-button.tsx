"use client";

import { LoaderCircle, Mic, Square } from "lucide-react";
import type { MicState } from "@/hooks/use-speech-input";
import type { VoiceLang } from "@/lib/api";
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
        "relative flex size-11 shrink-0 items-center justify-center rounded-full transition-all",
        active
          ? "bg-destructive text-white"
          : "bg-primary-soft text-primary hover:bg-primary hover:text-primary-foreground active:scale-95",
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
        <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden />
      ) : active ? (
        <Square className="relative size-5 fill-current" aria-hidden />
      ) : (
        <Mic className="size-5" aria-hidden />
      )}
    </button>
  );
}

interface VoiceLangToggleProps {
  lang: VoiceLang;
  onChange: (lang: VoiceLang) => void;
  disabled?: boolean;
}

const LANG_OPTIONS: { id: VoiceLang; label: string; name: string }[] = [
  { id: "bn", label: "বাং", name: "বাংলায় বলব" },
  { id: "en", label: "EN", name: "ইংরেজিতে বলব" },
];

/** Which language the user will speak: the recognizer writes in that language's script. */
export function VoiceLangToggle({ lang, onChange, disabled }: VoiceLangToggleProps) {
  return (
    <div role="radiogroup" aria-label="কোন ভাষায় বলবেন" className="flex h-9 items-center rounded-full border bg-background p-0.5 text-xs">
      {LANG_OPTIONS.map((opt) => (
        <button
          key={opt.id}
          type="button"
          role="radio"
          aria-checked={lang === opt.id}
          aria-label={opt.name}
          disabled={disabled}
          onClick={() => onChange(opt.id)}
          className={cn(
            "h-full rounded-full px-2.5 leading-tight transition-colors disabled:opacity-60",
            lang === opt.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
