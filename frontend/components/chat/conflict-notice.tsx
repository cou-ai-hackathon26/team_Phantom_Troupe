"use client";

import { Scale } from "lucide-react";
import { toBnDigits } from "@/lib/bn";
import type { Citation, ConflictAnalysis, ConflictItem, ConflictSource } from "@/lib/types";
import { cn } from "@/lib/utils";

const UNRESOLVED = new Set(["UNRESOLVED_OFFICIAL_DISAGREEMENT", "UNRESOLVED_INSUFFICIENT_METADATA"]);
const RESOLVED_WHY: Record<string, string> = {
  RESOLVED_BY_SOURCE_STATUS: "অন্য সূত্রটি একটি রহিত আইনের",
  RESOLVED_BY_EXPLICIT_SUPERSESSION: "পরের সংশোধনী আইন অন্য সূত্রটি সংশোধন করেছে",
};

interface ConflictNoticeProps {
  analysis: ConflictAnalysis | null | undefined;
  citations: Citation[];
  onCite: (citation: Citation) => void;
}

/** Shown only when the answer's sources disagree; normal answers render nothing here. */
export function ConflictNotice({ analysis, citations, onCite }: ConflictNoticeProps) {
  const shown = (analysis?.items ?? []).filter(
    (i) => i.disclosed && (UNRESOLVED.has(i.resolution ?? "") || (i.resolution ?? "") in RESOLVED_WHY),
  );
  if (shown.length === 0) return null;
  const unresolved = shown.some((i) => UNRESOLVED.has(i.resolution ?? ""));
  return (
    <section
      role="note"
      aria-label={unresolved ? "সরকারি নথিতে ভিন্ন তথ্য" : "রহিত বা সংশোধিত সূত্র"}
      className={cn("space-y-3 rounded-xl border p-3 text-[0.95rem]", unresolved ? "border-status-partial/50 bg-status-partial-bg" : "bg-background/60")}
    >
      <h3 className={cn("flex items-center gap-2 font-semibold", unresolved && "text-status-partial")}>
        <Scale className="size-4 shrink-0" aria-hidden />
        {unresolved ? "সরকারি নথিতে ভিন্ন তথ্য" : "রহিত বা সংশোধিত সূত্র বাদ দেওয়া হয়েছে"}
      </h3>
      {shown.map((item) => (
        <ConflictRow key={item.id} item={item} citations={citations} onCite={onCite} />
      ))}
    </section>
  );
}

function ConflictRow({ item, citations, onCite }: { item: ConflictItem; citations: Citation[]; onCite: (c: Citation) => void }) {
  const unresolved = UNRESOLVED.has(item.resolution ?? "");
  return (
    <div className="space-y-1.5">
      <p className="font-medium">{item.topic}</p>
      <ul className="space-y-1.5">
        {item.sources.map((s) => (
          <SourceValue
            key={s.chunk_id}
            source={s}
            applies={!unresolved && item.controlling_chunk_id === s.chunk_id}
            citation={citations.find((c) => c.marker === s.marker)}
            onCite={onCite}
          />
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">
        {unresolved
          ? item.resolution === "UNRESOLVED_OFFICIAL_DISAGREEMENT"
            ? "কোনটি এখন প্রযোজ্য, তা নথি থেকে নিশ্চিত করা যায়নি। আবেদনের আগে সংশ্লিষ্ট অফিস থেকে নিশ্চিত হোন।"
            : "দুটি তথ্য একই ক্ষেত্রে প্রযোজ্য কি না, নথি থেকে নিশ্চিত নয়। আবেদনের আগে সংশ্লিষ্ট অফিস থেকে নিশ্চিত হোন।"
          : `${RESOLVED_WHY[item.resolution ?? ""] ?? ""}।`}
      </p>
    </div>
  );
}

function SourceValue({
  source,
  applies,
  citation,
  onCite,
}: {
  source: ConflictSource;
  applies: boolean;
  citation: Citation | undefined;
  onCite: (c: Citation) => void;
}) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="font-semibold">{source.value}</span>
      <span className="text-sm text-muted-foreground">
        {source.source_type_label} · {source.title}
        {source.title_year !== null && ` · শিরোনামে সাল ${toBnDigits(source.title_year)}`}
      </span>
      {source.status === "repealed" && <span className="rounded border px-1.5 text-xs">রহিত</span>}
      {applies && <span className="rounded border border-primary/40 px-1.5 text-xs text-primary">প্রযোজ্য</span>}
      {citation && (
        <button
          type="button"
          onClick={() => onCite(citation)}
          aria-label={`সূত্র ${toBnDigits(citation.marker)} দেখুন`}
          className="rounded bg-primary-soft px-1.5 text-sm font-semibold text-primary hover:underline"
        >
          [{toBnDigits(citation.marker)}]
        </button>
      )}
    </li>
  );
}
