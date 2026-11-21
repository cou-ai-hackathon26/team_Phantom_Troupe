"use client";

import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";

interface Metric {
  value: number | null;
  n: number;
}

interface EvalResults {
  created_at: string;
  model: string;
  corpus_chunks: number;
  areas_indexed: string[];
  summary: {
    n_rows: number;
    n_completed: number;
    status_counts: Record<string, number>;
    area_detection_accuracy: Metric;
    correct_refusal_rate: Metric;
    false_answer_rate: Metric;
    citation_validity_rate: Metric;
    "recall@5": Metric;
    mrr: Metric;
    must_include_coverage: Metric;
    latency_ms: { p50: number | null; p95: number | null; n: number };
    unlabelled_rows: number;
  };
  ablation: Record<"dense" | "bm25" | "hybrid", { n: number; "recall@5": number | null; mrr: number | null }>;
}

function pct(m: Metric): string {
  return m.value === null ? "—" : `${toBnDigits((m.value * 100).toFixed(0))}%`;
}

function n(m: { n: number }): string {
  return toBnDigits(m.n);
}

const ROWS: [keyof EvalResults["summary"], string, string][] = [
  ["correct_refusal_rate", "বিষয়বহির্ভূত প্রশ্নে সঠিকভাবে উত্তর না দেওয়া", "বেশি ভালো"],
  ["false_answer_rate", "যেখানে উত্তর দেওয়ার কথা নয়, সেখানে উত্তর", "কম ভালো"],
  ["citation_validity_rate", "সূত্রগুলো সত্যিই খুঁজে পাওয়া নথি থেকে", "বেশি ভালো"],
  ["area_detection_accuracy", "বিষয় সঠিকভাবে চেনা (জমি/জিডি/ভাতা/শ্রম)", "বেশি ভালো"],
  ["recall@5", "সঠিক নথি-অংশ সেরা ৫টির মধ্যে (Recall@5)", "বেশি ভালো"],
  ["must_include_coverage", "উত্তরে জরুরি তথ্য আছে", "বেশি ভালো"],
];

export function EvalSection() {
  const [data, setData] = useState<EvalResults | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    request<EvalResults>("/eval/latest")
      .then(setData)
      .catch(() => setMissing(true));
  }, []);

  return (
    <section aria-labelledby="eval-heading" className="space-y-3">
      <h2 id="eval-heading" className="text-xl font-semibold">মূল্যায়ন</h2>
      {missing && <p className="text-muted-foreground">এখনো কোনো মূল্যায়ন চালানো হয়নি।</p>}
      {!data && !missing && <p className="text-muted-foreground">লোড হচ্ছে…</p>}
      {data && (
        <>
          <p className="text-[0.95rem] text-muted-foreground">
            {toBnDigits(data.summary.n_completed)}টি পরীক্ষামূলক প্রশ্নে পুরো ব্যবস্থা চালিয়ে পাওয়া ফল (মডেল {data.model},{" "}
            {new Date(data.created_at).toLocaleDateString("bn-BD", { day: "numeric", month: "long", year: "numeric" })})।
            শুধু মাপা সংখ্যা দেখানো হয়েছে; “—” মানে এর জন্য এখনো যাচাই করা উত্তর-তালিকা তৈরি হয়নি।
          </p>
          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[30rem] border-collapse rounded-xl text-[0.95rem]">
              <thead>
                <tr className="border-b text-left text-sm text-muted-foreground">
                  <th scope="col" className="py-2 pr-3 font-semibold">মাপকাঠি</th>
                  <th scope="col" className="px-2 py-2 text-right font-semibold">ফল</th>
                  <th scope="col" className="py-2 pl-2 text-right font-semibold">প্রশ্ন</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map(([key, label, hint]) => {
                  const m = data.summary[key] as Metric;
                  return (
                    <tr key={key} className="border-b last:border-0">
                      <td className="py-2 pr-3">
                        {label} <span className="text-xs text-muted-foreground">({hint})</span>
                      </td>
                      <td className="px-2 py-2 text-right font-semibold tabular-nums">{pct(m)}</td>
                      <td className="py-2 pl-2 text-right tabular-nums text-muted-foreground">{n(m)}</td>
                    </tr>
                  );
                })}
                <tr>
                  <td className="py-2 pr-3">উত্তরের সময় (মাঝামাঝি / সবচেয়ে ধীর ৫%)</td>
                  <td className="px-2 py-2 text-right font-semibold tabular-nums">
                    {data.summary.latency_ms.p50 === null
                      ? "—"
                      : `${toBnDigits((data.summary.latency_ms.p50 / 1000).toFixed(1))} / ${toBnDigits(((data.summary.latency_ms.p95 ?? 0) / 1000).toFixed(1))} সে.`}
                  </td>
                  <td className="py-2 pl-2 text-right tabular-nums text-muted-foreground">{n(data.summary.latency_ms)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {data.ablation.hybrid.n > 0 && (
            <div className="rounded-xl border bg-card p-4 text-[0.95rem]">
              <p className="font-semibold">খোঁজার পদ্ধতির তুলনা (Recall@5 · MRR)</p>
              <ul className="mt-1 space-y-0.5">
                {(["dense", "bm25", "hybrid"] as const).map((mode) => (
                  <li key={mode} className="tabular-nums">
                    {mode === "dense" ? "শুধু অর্থভিত্তিক" : mode === "bm25" ? "শুধু শব্দভিত্তিক" : "দুটো একসাথে (RRF)"}:{" "}
                    {toBnDigits(data.ablation[mode]["recall@5"]?.toFixed(2) ?? "—")} ·{" "}
                    {toBnDigits(data.ablation[mode].mrr?.toFixed(2) ?? "—")}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-sm text-muted-foreground">
            এই মূল্যায়ন চালানোর সময় জ্ঞানভান্ডারে {toBnDigits(data.corpus_chunks)}টি নথি-অংশ ছিল। নতুন নথি যুক্ত হলে ফল বদলাতে
            পারে; সর্বশেষ ফলের জন্য মূল্যায়ন আবার চালাতে হয়।
          </p>
        </>
      )}
    </section>
  );
}
