"use client";

import { useState } from "react";
import { Check, Copy, Phone, ThumbsDown, ThumbsUp, TriangleAlert } from "lucide-react";
import { sendFeedback } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { ChatResponse, Citation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AnswerText } from "./answer-text";
import { StatusBadge } from "./status-badge";
import { TracePanel } from "./trace-panel";

interface AnswerCardProps {
  response: ChatResponse;
  onCite: (citation: Citation) => void;
}

function plainText(response: ChatResponse): string {
  const sources = response.citations.map((c) => `[${toBnDigits(c.marker)}] ${c.citation} — ${c.title}`).join("\n");
  return sources ? `${response.answer}\n\nসূত্র:\n${sources}` : response.answer;
}

export function AnswerCard({ response, onCite }: AnswerCardProps) {
  const [copied, setCopied] = useState(false);
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const refused = response.status === "refused";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(plainText(response));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked: ignore */
    }
  };

  const rate = (value: "up" | "down") => {
    setRating(value);
    void sendFeedback(response.request_id, value).catch(() => undefined);
  };

  return (
    <article
      className={cn(
        "space-y-4 rounded-xl border bg-card p-4 sm:p-5",
        response.status === "partial" && "border-status-partial/40",
      )}
      aria-label="উত্তর"
    >
      <StatusBadge status={response.status} />

      {refused ? (
        <div className="space-y-4">
          <p className="text-[1.05rem] leading-[1.8]">{response.answer}</p>
          <a
            href="tel:333"
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-lg font-semibold text-primary-foreground hover:bg-primary/90"
          >
            <Phone className="size-5" aria-hidden /> ৩৩৩-এ কল করুন
          </a>
        </div>
      ) : (
        <AnswerText text={response.answer} citations={response.citations} onCite={onCite} />
      )}

      {response.warnings.length > 0 && (
        <div className="flex gap-2 rounded-lg bg-status-partial-bg p-3 text-status-partial" role="note">
          <TriangleAlert className="mt-1 size-4 shrink-0" aria-hidden />
          <div className="space-y-1">
            {response.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        </div>
      )}

      {response.citations.length > 0 && (
        <section aria-label="সূত্র" className="space-y-2 border-t pt-4">
          <h3 className="font-semibold">সূত্র</h3>
          <ol className="space-y-1.5">
            {response.citations.map((c) => (
              <li key={c.chunk_id}>
                <button
                  type="button"
                  onClick={() => onCite(c)}
                  className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-secondary"
                >
                  <span className="mt-0.5 rounded-md bg-primary-soft px-1.5 text-sm font-semibold text-primary">
                    {toBnDigits(c.marker)}
                  </span>
                  <span className="min-w-0">
                    <span className="font-semibold">{c.citation}</span>
                    <span className="text-muted-foreground"> — {c.title}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}

      {response.status !== "clarify" && (
        <div className="flex flex-wrap items-center gap-1 border-t pt-3 text-sm">
          <button
            type="button"
            onClick={() => void copy()}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            {copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
            {copied ? "কপি হয়েছে" : "কপি"}
          </button>
          <span className="ml-auto text-muted-foreground" id={`fb-${response.request_id}`}>
            {rating ? "ধন্যবাদ!" : "উত্তরটি কাজে লেগেছে?"}
          </span>
          <button
            type="button"
            onClick={() => rate("up")}
            aria-pressed={rating === "up"}
            aria-label="হ্যাঁ, কাজে লেগেছে"
            disabled={rating !== null}
            className={cn("rounded-lg p-2 hover:bg-secondary", rating === "up" && "text-primary")}
          >
            <ThumbsUp className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => rate("down")}
            aria-pressed={rating === "down"}
            aria-label="না, কাজে লাগেনি"
            disabled={rating !== null}
            className={cn("rounded-lg p-2 hover:bg-secondary", rating === "down" && "text-destructive")}
          >
            <ThumbsDown className="size-4" aria-hidden />
          </button>
        </div>
      )}

      <TracePanel response={response} />
    </article>
  );
}
