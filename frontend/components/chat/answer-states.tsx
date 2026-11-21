"use client";

import { useEffect, useState } from "react";
import { Check, FileText, RefreshCw, TriangleAlert } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** The assistant's round mark, shown beside every answer. */
export function AssistantAvatar({ className }: { className?: string }) {
  return <BrandMark className={cn("size-8 rounded-[0.6rem] shadow-card sm:size-9", className)} />;
}

// what the pipeline is doing; advanced on a timer (the API answers in one response)
const STAGES = ["প্রশ্নটি বুঝছি", "সরকারি নথি খুঁজছি", "উত্তর লিখছি", "সূত্র যাচাই করছি"];
const STAGE_MS = [1200, 2600, 3500];

export function AnswerSkeleton() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (stage >= STAGES.length - 1) return;
    const t = setTimeout(() => setStage((s) => s + 1), STAGE_MS[stage]);
    return () => clearTimeout(t);
  }, [stage]);

  return (
    <div className="flex animate-fade-up gap-2.5 sm:gap-3" aria-busy="true">
      <AssistantAvatar className="animate-pulse motion-reduce:animate-none" />
      <div className="min-w-0 flex-1 space-y-4 rounded-2xl rounded-tl-md border bg-card p-4 shadow-card sm:p-5">
        <ol className="space-y-1.5" aria-live="polite">
          {STAGES.map((label, i) => (
            <li
              key={label}
              className={cn(
                "flex items-center gap-2 text-[0.95rem] transition-opacity duration-300",
                i > stage ? "opacity-0" : "opacity-100",
                i < stage ? "text-muted-foreground" : "font-medium",
              )}
              aria-hidden={i > stage}
            >
              {i < stage ? (
                <span className="flex size-4 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Check className="size-3" strokeWidth={3} aria-hidden />
                </span>
              ) : (
                <span className="flex size-4 items-center justify-center gap-0.5" aria-hidden>
                  {[0, 1, 2].map((d) => (
                    <span
                      key={d}
                      className="size-1 animate-dots rounded-full bg-primary motion-reduce:animate-none"
                      style={{ animationDelay: `${d * 160}ms` }}
                    />
                  ))}
                </span>
              )}
              {label}
              {i === stage && "…"}
            </li>
          ))}
        </ol>
        <div className="space-y-2.5">
          <Skeleton className="h-3.5 w-11/12" />
          <Skeleton className="h-3.5 w-9/12" />
          <Skeleton className="h-3.5 w-10/12" />
        </div>
      </div>
    </div>
  );
}

export function AnswerError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex animate-fade-up gap-2.5 sm:gap-3">
      <AssistantAvatar />
      <div
        className="flex min-w-0 flex-1 flex-col gap-3 rounded-2xl rounded-tl-md border border-destructive/30 bg-card p-4 sm:flex-row sm:items-center"
        role="alert"
      >
        <div className="flex flex-1 gap-2">
          <TriangleAlert className="mt-1 size-5 shrink-0 text-destructive" aria-hidden />
          <p>{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2 font-semibold transition-colors hover:bg-secondary"
        >
          <RefreshCw className="size-4" aria-hidden /> আবার চেষ্টা করুন
        </button>
      </div>
    </div>
  );
}

export function UserBubble({ text, attachment }: { text: string; attachment?: string }) {
  return (
    <div className="flex animate-fade-up flex-col items-end gap-1">
      {attachment && (
        <span className="inline-flex max-w-[85%] items-center gap-1.5 truncate rounded-full border bg-card px-2.5 py-0.5 text-sm text-muted-foreground">
          <FileText className="size-3.5 shrink-0" aria-hidden /> {attachment}
        </span>
      )}
      <p className="max-w-[88%] rounded-2xl rounded-br-md bg-gradient-to-br from-primary to-[#0d7d5a] px-4 py-2.5 text-[1.03rem] leading-relaxed whitespace-pre-line text-primary-foreground shadow-card sm:max-w-[80%]">
        {text}
      </p>
    </div>
  );
}
