"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { ArrowUp } from "lucide-react";

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
  mic: ReactNode; // the voice button
  attach?: ReactNode; // personal-document button
  top?: ReactNode; // attached-document chip
  hint?: ReactNode;
}

export function Composer({ value, onChange, onSubmit, busy, mic, attach, top, hint }: ComposerProps) {
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
    <div className="border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
      <div className="mx-auto max-w-3xl px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {top}
        <form
          className="flex items-end gap-2 sm:gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSend) onSubmit();
          }}
        >
          {mic}
          {attach}
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
            placeholder="প্রশ্ন লিখুন…"
            maxLength={2000}
            className="min-h-12 min-w-0 flex-1 resize-none rounded-2xl border bg-card px-3 py-3 sm:min-h-14 sm:px-4 sm:py-3.5 text-[1.05rem] leading-relaxed outline-none placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/25"
          />
          <button
            type="submit"
            disabled={!canSend}
            aria-label="প্রশ্ন পাঠান"
            className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary sm:size-14 text-primary-foreground transition-colors hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground"
          >
            <ArrowUp className="size-6" aria-hidden />
          </button>
        </form>
        {hint}
        <p className="mt-2 text-center text-xs text-muted-foreground">
          এটি আইনি পরামর্শ নয়; তথ্য যাচাই করতে সংশ্লিষ্ট অফিসে যোগাযোগ করুন।
        </p>
      </div>
    </div>
  );
}
