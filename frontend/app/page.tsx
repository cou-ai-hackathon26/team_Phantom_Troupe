"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { AnswerCard } from "@/components/chat/answer-card";
import { AnswerError, AnswerSkeleton, UserBubble } from "@/components/chat/answer-states";
import { AreaCards } from "@/components/chat/area-cards";
import { CitationSheet, type SourceView } from "@/components/chat/citation-sheet";
import { Composer } from "@/components/chat/composer";
import { ApiError, askQuestion, getChunk } from "@/lib/api";
import type { ChatResponse, Citation } from "@/lib/types";

interface Turn {
  id: number;
  question: string;
  state: "loading" | "done" | "error";
  response?: ChatResponse;
  error?: string;
}

const STATUS_ANNOUNCE: Record<ChatResponse["status"], string> = {
  answered: "উত্তর পাওয়া গেছে",
  partial: "আংশিক যাচাই করা উত্তর",
  refused: "উত্তর পাওয়া যায়নি",
  clarify: "আরও তথ্য দরকার",
};

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]); // session memory only — nothing is stored
  const [input, setInput] = useState("");
  const [source, setSource] = useState<SourceView | null>(null);
  const [announce, setAnnounce] = useState("");
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.state === "loading");

  const run = useCallback(async (id: number, question: string) => {
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "loading", error: undefined } : t)));
    try {
      const response = await askQuestion({ message: question, debug: true });
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "done", response } : t)));
      setAnnounce(`${STATUS_ANNOUNCE[response.status]}। ${response.answer}`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "কিছু একটা সমস্যা হয়েছে। আবার চেষ্টা করুন।";
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "error", error: message } : t)));
      setAnnounce(message);
    }
  }, []);

  const ask = useCallback(
    (raw: string) => {
      const question = raw.trim();
      if (question.length < 2 || busy) return;
      const id = nextId.current++;
      setTurns((prev) => [...prev, { id, question, state: "loading" }]);
      setInput("");
      void run(id, question);
    },
    [busy, run],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const openCitation = (c: Citation) => {
    const base: SourceView = {
      marker: c.marker,
      citation: c.citation,
      title: c.title,
      text: c.excerpt,
      notes: c.notes,
      sourceUrl: c.source_url,
      loading: true,
    };
    setSource(base);
    getChunk(c.chunk_id)
      .then((chunk) => setSource((cur) => (cur?.citation === c.citation ? { ...base, text: chunk.text, loading: false } : cur)))
      .catch(() => setSource((cur) => (cur?.citation === c.citation ? { ...base, loading: false } : cur)));
  };

  return (
    <div className="flex min-h-[calc(100dvh-4.5rem)] flex-col">
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:py-8">
        {turns.length === 0 ? (
          <AreaCards onAsk={ask} disabled={busy} />
        ) : (
          <div className="space-y-6">
            {turns.map((turn) => (
              <div key={turn.id} className="space-y-3">
                <UserBubble text={turn.question} />
                {turn.state === "loading" && <AnswerSkeleton />}
                {turn.state === "error" && (
                  <AnswerError message={turn.error ?? ""} onRetry={() => void run(turn.id, turn.question)} />
                )}
                {turn.state === "done" && turn.response && <AnswerCard response={turn.response} onCite={openCitation} />}
              </div>
            ))}
          </div>
        )}
        <div ref={endRef} />
        <p className="sr-only" aria-live="polite">
          {announce}
        </p>
      </main>

      <div className="sticky bottom-0 z-20">
        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => ask(input)}
          busy={busy}
          mic={
            <button
              type="button"
              disabled
              aria-label="মাইকে প্রশ্ন বলুন (শীঘ্রই)"
              className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground disabled:opacity-50 sm:size-16"
            >
              <Mic className="size-6" aria-hidden />
            </button>
          }
        />
      </div>

      <CitationSheet source={source} onOpenChange={(open) => !open && setSource(null)} />
    </div>
  );
}
