"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { ArrowUp, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
  mic: ReactNode; // the voice button
  lang?: ReactNode; // spoken-language toggle
  attach?: ReactNode; // personal-document button
  top?: ReactNode; // attached-document chip
  hint?: ReactNode;
}

/** Message box: full-width text area on top, tools and send button in a row below (works at phone width). */
export function Composer({ value, onChange, onSubmit, busy, mic, lang, attach, top, hint }: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // grow with content up to ~5 lines
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (value.trim().length >= 2 && !busy) onSubmit();
    }
  };

  const canSend = value.trim().length >= 2 && !busy;

  return (
    <div className="bg-gradient-to-t from-background via-background/95 to-transparent pt-4">
      <div className="mx-auto max-w-3xl px-3 pb-[max(0.6rem,env(safe-area-inset-bottom))] sm:px-4">
        {top}
        <form
          className="group rounded-3xl border bg-card p-2 shadow-card transition-shadow focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-primary/10"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSend) onSubmit();
          }}
        >
          <label htmlFor="question" className="sr-only">
            আপনার প্রশ্ন
          </label>
          <textarea
            id="question"
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="আপনার প্রশ্ন লিখুন বা মাইকে বলুন…"
            maxLength={2000}
            className="block max-h-40 min-h-11 w-full resize-none bg-transparent px-3 pt-2 pb-1 text-[1.05rem] leading-relaxed outline-none placeholder:text-muted-foreground"
          />
          <div className="flex items-center gap-1.5 pt-1">
            {attach}
            {lang}
            <span className="flex-1" />
            {value.length > 1500 && (
              <span className="text-xs text-muted-foreground tabular-nums">{2000 - value.length}</span>
            )}
            {mic}
            <button
              type="submit"
              disabled={!canSend}
              aria-label="প্রশ্ন পাঠান"
              className={cn(
                "flex size-11 shrink-0 items-center justify-center rounded-full transition-all",
                canSend
                  ? "bg-primary text-primary-foreground shadow-card hover:scale-105 hover:bg-primary/90 active:scale-95"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {busy ? (
                <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden />
              ) : (
                <ArrowUp className="size-5" aria-hidden />
              )}
            </button>
          </div>
        </form>
        {hint}
        <p className="mt-1.5 text-center text-[0.72rem] text-muted-foreground sm:text-xs">
          এটি আইনি পরামর্শ নয়; তথ্য যাচাই করতে সংশ্লিষ্ট অফিসে যোগাযোগ করুন।
        </p>
      </div>
    </div>
  );
}
