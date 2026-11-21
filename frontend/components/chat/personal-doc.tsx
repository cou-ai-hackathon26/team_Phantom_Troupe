"use client";

import { useRef } from "react";
import { FileText, LoaderCircle, Paperclip, X } from "lucide-react";
import { toBnDigits } from "@/lib/bn";
import type { UserDocInfo } from "@/lib/types";

const ACCEPT = "application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp";

export function AttachButton({ onPick, busy, disabled }: { onPick: (file: File) => void; busy: boolean; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onPick(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={disabled || busy}
        aria-label={busy ? "নথি পড়া হচ্ছে" : "নিজের নথি যুক্ত করুন (PDF বা ছবি)"}
        title="নিজের নথি যুক্ত করুন (PDF বা ছবি)"
        className="flex size-10 shrink-0 items-center justify-center self-center rounded-full border sm:size-11 bg-card text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary disabled:opacity-60"
      >
        {busy ? <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden /> : <Paperclip className="size-5" aria-hidden />}
      </button>
    </>
  );
}

interface DocChipProps {
  doc: UserDocInfo | null;
  uploading: string | null; // filename being read
  error: string | null;
  onRemove: () => void;
  onDismissError: () => void;
}

export function PersonalDocChip({ doc, uploading, error, onRemove, onDismissError }: DocChipProps) {
  if (uploading) {
    return (
      <p className="mb-2 flex items-center gap-2 rounded-xl border bg-card px-3 py-2 text-[0.95rem]" aria-live="polite">
        <LoaderCircle className="size-4 animate-spin text-primary motion-reduce:animate-none" aria-hidden />
        <span className="min-w-0 truncate">“{uploading}” পড়া হচ্ছে… (স্ক্যান করা নথিতে OCR লাগে, একটু সময় নিতে পারে)</span>
      </p>
    );
  }
  if (error) {
    return (
      <p className="mb-2 flex items-start justify-between gap-2 rounded-xl bg-status-partial-bg px-3 py-2 text-[0.95rem] text-status-partial" role="alert">
        <span>{error}</span>
        <button type="button" onClick={onDismissError} className="shrink-0 font-semibold">ঠিক আছে</button>
      </p>
    );
  }
  if (!doc) return null;
  const ocr = doc.methods.some((m) => m !== "pymupdf");
  return (
    <div className="mb-2 rounded-xl border border-primary/30 bg-primary-soft/60 px-3 py-2">
      <div className="flex items-center gap-2">
        <FileText className="size-4 shrink-0 text-primary" aria-hidden />
        <p className="min-w-0 flex-1 truncate text-[0.95rem]">
          <span className="font-semibold">আপনার নথি:</span> {doc.filename}
          <span className="text-muted-foreground">
            {" "}· {toBnDigits(doc.pages)} পৃষ্ঠা{ocr ? " · OCR" : ""}
          </span>
        </p>
        <button type="button" onClick={onRemove} aria-label="নথিটি সরান" className="rounded-md p-1 text-muted-foreground hover:bg-background hover:text-foreground">
          <X className="size-4" aria-hidden />
        </button>
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">
        এখন প্রশ্ন করলে এই নথি থেকেও উত্তর খোঁজা হবে। নথিটি সংরক্ষণ বা জ্ঞানভান্ডারে যুক্ত করা হয় না; ১ ঘণ্টা পর মুছে যায়।
        {doc.needs_review && " কিছু অংশ অস্পষ্টভাবে পড়া গেছে।"}
      </p>
    </div>
  );
}
