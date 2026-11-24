"use client";

import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { areaLabel } from "@/lib/areas";
import { formatMs, formatScore, toBnDigits } from "@/lib/bn";
import type { ChatResponse, FollowupIntent } from "@/lib/types";

const FOLLOWUP_LABEL: Record<FollowupIntent, string> = {
  CONTINUE: "আগের প্রশ্নের ধারাবাহিকতা — আগের সূত্র যাচাই করে আবার ব্যবহার",
  EXPAND: "আগের বিষয়ে নতুন তথ্য — আগের সূত্র যাচাই ও নতুন খোঁজ",
  NEW_TOPIC: "নতুন বিষয় — আগের সূত্র ব্যবহার হয়নি",
  CLARIFY: "কোন বিষয়ের কথা, তা স্পষ্ট নয় — প্রশ্ন করা হয়েছে",
};

const GATE_LABEL: Record<string, string> = {
  answered: "উত্তর তৈরি ও যাচাই সম্পন্ন",
  out_of_scope: "প্রশ্নটি চারটি বিষয়ের বাইরে",
  needs_clarification: "প্রশ্নটি আরও নির্দিষ্ট হওয়া দরকার",
  no_candidates: "এই বিষয়ে কোনো নথি পাওয়া যায়নি",
  cache: "আগের যাচাই করা উত্তর",
};

function gateLabel(gate: string): string {
  if (gate.startsWith("low_score")) return "নথির সাথে মিল খুব কম";
  if (gate.startsWith("validation")) return "যাচাইয়ে উত্তর বাতিল হয়েছে";
  return GATE_LABEL[gate] ?? gate;
}

function Rank({ value }: { value: number | null }) {
  return <span className={value === null ? "text-muted-foreground" : ""}>{value === null ? "—" : toBnDigits(value)}</span>;
}

/** "How this answer was found" — retrieval trace for the judges' demo. */
export function TracePanel({ response }: { response: ChatResponse }) {
  const trace = response.trace;
  if (!trace) return null;
  return (
    <Collapsible className="rounded-xl border bg-background">
      <CollapsibleTrigger className="group flex w-full items-center justify-between gap-2 px-4 py-3 text-left font-semibold">
        এই উত্তর কীভাবে পাওয়া গেল
        <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4 border-t px-4 py-4 text-[0.95rem]">
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-muted-foreground">প্রমিত প্রশ্ন</dt>
            <dd>{response.normalized_question}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">চিহ্নিত বিষয়</dt>
            <dd>{areaLabel(response.area)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">সিদ্ধান্ত</dt>
            <dd>{gateLabel(trace.gate)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">সময় · এআই কল</dt>
            <dd>
              {formatMs(response.latency_ms)} · {toBnDigits(trace.llm_calls)} বার
              {response.cached && " (ক্যাশ)"}
            </dd>
          </div>
          {trace.followup_intent && (
            <div className="sm:col-span-2">
              <dt className="text-sm text-muted-foreground">ফলো-আপ প্রশ্ন</dt>
              <dd>
                {FOLLOWUP_LABEL[trace.followup_intent]}
                {(trace.reused_chunk_ids?.length ?? 0) > 0 &&
                  ` · আবার ব্যবহৃত সূত্র: ${toBnDigits(trace.reused_chunk_ids?.length ?? 0)}টি`}
              </dd>
            </div>
          )}
        </dl>
        {trace.candidates.length > 0 && (
          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[34rem] border-collapse text-sm">
              <caption className="mb-2 text-left text-muted-foreground">
                সেরা {toBnDigits(trace.candidates.length)}টি নথি-অংশ: অর্থভিত্তিক (dense) ও শব্দভিত্তিক (BM25) খোঁজ,
                RRF দিয়ে একত্রিত
              </caption>
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th scope="col" className="py-2 pr-3 font-semibold">নথি-অংশ</th>
                  <th scope="col" className="px-2 py-2 text-right font-semibold">dense</th>
                  <th scope="col" className="px-2 py-2 text-right font-semibold">মিল</th>
                  <th scope="col" className="px-2 py-2 text-right font-semibold">BM25</th>
                  <th scope="col" className="py-2 pl-2 text-right font-semibold">RRF</th>
                </tr>
              </thead>
              <tbody>
                {trace.candidates.map((c) => (
                  <tr key={c.chunk_id} className="border-b last:border-0">
                    <td className="py-2 pr-3">
                      <span className="font-semibold">{c.citation.split(", ").slice(-1)[0]}</span>{" "}
                      <span className="text-muted-foreground">
                        {c.title}
                        {c.part !== null && ` (অংশ ${toBnDigits(c.part)})`}
                      </span>
                      {c.exact_section && (
                        <span className="ml-1 rounded bg-primary-soft px-1 text-xs text-primary">ধারা নম্বর মিলেছে</span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums"><Rank value={c.dense_rank} /></td>
                    <td className="px-2 py-2 text-right tabular-nums">{formatScore(c.dense_score)}</td>
                    <td className="px-2 py-2 text-right tabular-nums"><Rank value={c.bm25_rank} /></td>
                    <td className="py-2 pl-2 text-right tabular-nums">{formatScore(c.fused_score, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
