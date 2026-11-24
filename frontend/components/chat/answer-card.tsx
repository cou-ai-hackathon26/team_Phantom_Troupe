"use client";

import { useState } from "react";
import { BookOpenText, Check, Copy, ExternalLink, FileText, Globe, Phone, Share2, ThumbsDown, ThumbsUp, TriangleAlert } from "lucide-react";
import { sendFeedback } from "@/lib/api";
import { areaLabel } from "@/lib/areas";
import { toBnDigits } from "@/lib/bn";
import type { ChatResponse, Citation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AssistantAvatar } from "./answer-states";
import { AnswerText } from "./answer-text";
import { ConflictNotice } from "./conflict-notice";
import { ListenButton } from "./listen-button";
import { StatusBadge } from "./status-badge";
import { TracePanel } from "./trace-panel";

interface AnswerCardProps {
  response: ChatResponse;
  onCite: (citation: Citation) => void;
}

function plainText(response: ChatResponse): string {
  const sources = response.citations
    .map((c) => `[${toBnDigits(c.marker)}] ${c.citation} — ${c.title}${c.kind === "web" && c.source_url ? ` (${c.source_url})` : ""}`)
    .join("\n");
  return sources ? `${response.answer}\n\nসূত্র:\n${sources}` : response.answer;
}

function hostOf(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

const KIND_STYLE: Record<Citation["kind"], { icon: typeof FileText; chip: string; label: string }> = {
  official: { icon: BookOpenText, chip: "bg-primary-soft text-primary", label: "সরকারি নথি" },
  web: { icon: Globe, chip: "border border-dashed text-muted-foreground", label: "সরকারি ওয়েবসাইট · লিংকে যাচাই করুন" },
  user: { icon: FileText, chip: "bg-status-clarify-bg text-status-clarify", label: "আপনার নথি · সরকারি সূত্র নয়" },
};

function SourceItem({ c, onCite }: { c: Citation; onCite: (c: Citation) => void }) {
  const style = KIND_STYLE[c.kind];
  const Icon = style.icon;
  const host = c.kind === "web" ? hostOf(c.source_url) : "";
  return (
    <li className="min-w-0">
      <button
        type="button"
        onClick={() => onCite(c)}
        className="group flex w-full min-w-0 items-start gap-3 rounded-xl border bg-background/60 p-3 text-left transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-card"
      >
        <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg text-sm font-semibold", style.chip)}>
          {toBnDigits(c.marker)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 font-semibold leading-snug break-words">{c.citation}</span>
          <span className="mt-0.5 flex items-center gap-1 text-sm text-muted-foreground">
            <Icon className="size-3.5 shrink-0" aria-hidden />
            <span className="truncate">{c.kind === "official" ? c.title : host ? `${host} · ${style.label}` : style.label}</span>
          </span>
        </span>
        {c.kind === "web" ? (
          <ExternalLink className="mt-1 size-4 shrink-0 text-muted-foreground group-hover:text-primary" aria-hidden />
        ) : null}
      </button>
    </li>
  );
}

export function AnswerCard({ response, onCite }: AnswerCardProps) {
  const [copied, setCopied] = useState(false);
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const refused = response.status === "refused";
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(plainText(response));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked: ignore */
    }
  };

  const share = async () => {
    try {
      await navigator.share({ title: "অধিকারAI-এর উত্তর", text: plainText(response) });
    } catch {
      /* dismissed */
    }
  };

  const rate = (value: "up" | "down") => {
    setRating(value);
    void sendFeedback(response.request_id, value).catch(() => undefined);
  };

  return (
    <div className="flex animate-fade-up gap-2.5 sm:gap-3">
      <AssistantAvatar />
      <article
        className={cn(
          "min-w-0 flex-1 space-y-4 rounded-2xl rounded-tl-md border bg-card p-4 shadow-card sm:p-5",
          response.status === "partial" && "border-status-partial/40",
        )}
        aria-label="উত্তর"
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={response.status} />
          {response.area !== "unknown" && (
            <span className="rounded-full border px-2.5 py-0.5 text-sm text-muted-foreground">{areaLabel(response.area)}</span>
          )}
        </div>

        {refused ? (
          <div className="space-y-4">
            <p className="text-[1.05rem] leading-[1.8]">{response.answer}</p>
            <a
              href="tel:333"
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-lg font-semibold text-primary-foreground shadow-card transition-transform hover:scale-[1.02] hover:bg-primary/90 active:scale-95"
            >
              <Phone className="size-5" aria-hidden /> ৩৩৩-এ কল করুন
            </a>
          </div>
        ) : (
          <AnswerText text={response.answer} citations={response.citations} onCite={onCite} />
        )}

        {!refused && (
          <ConflictNotice analysis={response.conflict_analysis} citations={response.citations} onCite={onCite} />
        )}

        {response.warnings.length > 0 && (
          <div className="flex gap-2 rounded-xl bg-status-partial-bg p-3 text-[0.95rem] text-status-partial" role="note">
            <TriangleAlert className="mt-1 size-4 shrink-0" aria-hidden />
            <div className="space-y-1">
              {response.warnings.map((w) => (
                <p key={w}>{w}</p>
              ))}
            </div>
          </div>
        )}

        {response.citations.length > 0 && (
          <section aria-label="সূত্র" className="space-y-2.5 border-t pt-4">
            <h3 className="flex items-center gap-2 font-semibold">
              সূত্র
              <span className="rounded-full bg-secondary px-2 text-sm font-medium text-muted-foreground">
                {toBnDigits(response.citations.length)}
              </span>
            </h3>
            <ol className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {response.citations.map((c) => (
                <SourceItem key={c.chunk_id} c={c} onCite={onCite} />
              ))}
            </ol>
          </section>
        )}

        {response.status !== "clarify" && (
          <div className="flex flex-wrap items-center gap-1 border-t pt-3 text-sm">
            <ListenButton text={response.answer} token={response.speech_token} />
            <button
              type="button"
              onClick={() => void copy()}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              {copied ? <Check className="size-4 text-primary" aria-hidden /> : <Copy className="size-4" aria-hidden />}
              {copied ? "কপি হয়েছে" : "কপি"}
            </button>
            {canShare && (
              <button
                type="button"
                onClick={() => void share()}
                className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <Share2 className="size-4" aria-hidden /> শেয়ার
              </button>
            )}
            <span className="ml-auto hidden text-muted-foreground sm:inline" id={`fb-${response.request_id}`}>
              {rating ? "ধন্যবাদ!" : "উত্তরটি কাজে লেগেছে?"}
            </span>
            <span className="ml-auto text-muted-foreground sm:hidden">{rating ? "ধন্যবাদ!" : ""}</span>
            <button
              type="button"
              onClick={() => rate("up")}
              aria-pressed={rating === "up"}
              aria-label="হ্যাঁ, কাজে লেগেছে"
              disabled={rating !== null}
              className={cn(
                "rounded-lg p-2 transition-all hover:bg-secondary active:scale-90",
                rating === "up" && "bg-primary-soft text-primary",
              )}
            >
              <ThumbsUp className="size-4" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => rate("down")}
              aria-pressed={rating === "down"}
              aria-label="না, কাজে লাগেনি"
              disabled={rating !== null}
              className={cn(
                "rounded-lg p-2 transition-all hover:bg-secondary active:scale-90",
                rating === "down" && "bg-destructive/10 text-destructive",
              )}
            >
              <ThumbsDown className="size-4" aria-hidden />
            </button>
          </div>
        )}

        <TracePanel response={response} />
      </article>
    </div>
  );
}
