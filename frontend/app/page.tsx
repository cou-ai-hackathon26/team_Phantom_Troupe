"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnswerCard } from "@/components/chat/answer-card";
import { AnswerError, AnswerSkeleton, UserBubble } from "@/components/chat/answer-states";
import { AreaCards } from "@/components/chat/area-cards";
import { CitationSheet, type SourceView } from "@/components/chat/citation-sheet";
import { Composer } from "@/components/chat/composer";
import { MicButton } from "@/components/chat/mic-button";
import { AttachButton, PersonalDocChip } from "@/components/chat/personal-doc";
import { useSpeechInput } from "@/hooks/use-speech-input";
import { toBnDigits } from "@/lib/bn";
import { ApiError, askQuestion, deleteUserDoc, getChunk, uploadUserDoc } from "@/lib/api";
import type { ChatResponse, Citation, UserDocInfo } from "@/lib/types";

interface Turn {
  id: number;
  question: string;
  docId?: string; // personal document the question was asked about
  docName?: string;
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
  const [showMicHint, setShowMicHint] = useState(false);
  const [doc, setDoc] = useState<UserDocInfo | null>(null);
  const [docUploading, setDocUploading] = useState<string | null>(null);
  const [docError, setDocError] = useState<string | null>(null);

  const attachDoc = async (file: File) => {
    setDocError(null);
    if (file.size > 25 * 1024 * 1024) {
      setDocError("ফাইলটি ২৫ MB-এর বেশি। ছোট ফাইল দিন।");
      return;
    }
    setDocUploading(file.name);
    try {
      if (doc) void deleteUserDoc(doc.doc_id).catch(() => undefined);
      setDoc(await uploadUserDoc(file));
      requestAnimationFrame(() => document.getElementById("question")?.focus());
    } catch (err) {
      setDoc(null);
      setDocError(err instanceof ApiError ? err.message : "নথিটি পড়া যায়নি। আবার চেষ্টা করুন।");
    } finally {
      setDocUploading(null);
    }
  };

  const removeDoc = () => {
    if (doc) void deleteUserDoc(doc.doc_id).catch(() => undefined);
    setDoc(null);
  };

  // voice: final text goes into the input box for the user to check and edit — never auto-sent
  const voice = useSpeechInput((text) => {
    setInput(text);
    requestAnimationFrame(() => document.getElementById("question")?.focus());
  });

  useEffect(() => {
    try {
      setShowMicHint(window.localStorage.getItem("adhikarai.micHintSeen") !== "1");
    } catch {
      setShowMicHint(true);
    }
  }, []);

  const startVoice = () => {
    setShowMicHint(false);
    try {
      window.localStorage.setItem("adhikarai.micHintSeen", "1");
    } catch {
      /* storage blocked: hint simply shows again next time */
    }
    voice.start();
  };

  const run = useCallback(async (id: number, question: string, docId?: string) => {
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "loading", error: undefined } : t)));
    try {
      const response = await askQuestion({ message: question, debug: true, user_doc_id: docId });
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "done", response } : t)));
      setAnnounce(`${STATUS_ANNOUNCE[response.status]}। ${response.answer}`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "কিছু একটা সমস্যা হয়েছে। আবার চেষ্টা করুন।";
      if (err instanceof ApiError && err.code === "user_doc_expired") setDoc(null);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, state: "error", error: message } : t)));
      setAnnounce(message);
    }
  }, []);

  const ask = useCallback(
    (raw: string) => {
      const question = raw.trim();
      if (question.length < 2 || busy) return;
      const id = nextId.current++;
      setTurns((prev) => [...prev, { id, question, state: "loading", docId: doc?.doc_id, docName: doc?.filename }]);
      setInput("");
      void run(id, question, doc?.doc_id);
    },
    [busy, run, doc],
  );

  useEffect(() => {
    // follow the conversation, but never scroll the empty home screen away from its heading
    if (turns.length > 0) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const openCitation = (c: Citation) => {
    if (c.kind === "user") {
      // the user's own document: show the passage we already have; it is not in the knowledge base
      setSource({ marker: c.marker, citation: c.citation, title: c.title, text: c.excerpt, notes: [], sourceUrl: null, personal: true });
      return;
    }
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
                <UserBubble text={turn.question} attachment={turn.docName} />
                {turn.state === "loading" && <AnswerSkeleton />}
                {turn.state === "error" && (
                  <AnswerError message={turn.error ?? ""} onRetry={() => void run(turn.id, turn.question, turn.docId)} />
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
          mic={<MicButton state={voice.state} onStart={startVoice} onStop={voice.stop} disabled={busy} />}
          attach={<AttachButton onPick={(f) => void attachDoc(f)} busy={docUploading !== null} disabled={busy} />}
          top={
            <PersonalDocChip
              doc={doc}
              uploading={docUploading}
              error={docError}
              onRemove={removeDoc}
              onDismissError={() => setDocError(null)}
            />
          }
          hint={
            <VoiceStatus
              state={voice.state}
              interim={voice.interim}
              error={voice.error}
              elapsed={voice.elapsed}
              maxSeconds={voice.maxSeconds}
              showHint={showMicHint && voice.mode !== "none"}
              onDismissError={voice.clearError}
            />
          }
        />
      </div>

      <CitationSheet source={source} onOpenChange={(open) => !open && setSource(null)} />
    </div>
  );
}

interface VoiceStatusProps {
  state: ReturnType<typeof useSpeechInput>["state"];
  interim: string;
  error: string | null;
  elapsed: number;
  maxSeconds: number;
  showHint: boolean;
  onDismissError: () => void;
}

function VoiceStatus({ state, interim, error, elapsed, maxSeconds, showHint, onDismissError }: VoiceStatusProps) {
  if (state === "listening") {
    return (
      <p className="mt-2 rounded-xl bg-primary-soft px-3 py-2 text-[0.98rem]" aria-live="polite">
        <span className="font-semibold text-primary">শুনছি… </span>
        {interim || <span className="text-muted-foreground">আপনার ভাষায় প্রশ্নটি বলুন, শেষ হলে থামুন।</span>}
      </p>
    );
  }
  if (state === "recording") {
    return (
      <p className="mt-2 rounded-xl bg-primary-soft px-3 py-2 text-[0.98rem]" aria-live="polite">
        <span className="font-semibold text-primary">রেকর্ড হচ্ছে… </span>
        {toBnDigits(elapsed)}/{toBnDigits(maxSeconds)} সেকেন্ড। বলা শেষ হলে লাল বোতামে চাপ দিন।
      </p>
    );
  }
  if (state === "transcribing") {
    return (
      <p className="mt-2 text-[0.98rem] text-muted-foreground" aria-live="polite">
        কথা লেখায় রূপান্তর হচ্ছে…
      </p>
    );
  }
  if (error) {
    return (
      <p className="mt-2 flex items-start justify-between gap-2 rounded-xl bg-status-partial-bg px-3 py-2 text-[0.95rem] text-status-partial" role="alert">
        <span>{error}</span>
        <button type="button" onClick={onDismissError} className="shrink-0 font-semibold underline-offset-4 hover:underline">
          ঠিক আছে
        </button>
      </p>
    );
  }
  if (showHint) {
    return <p className="mt-2 text-center text-sm text-primary">মাইকে চাপ দিয়ে আপনার ভাষায় প্রশ্ন বলুন</p>;
  }
  return null;
}
