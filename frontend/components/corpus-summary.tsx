"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { AREAS } from "@/lib/areas";
import { listSources } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { DocumentSummary } from "@/lib/types";

/** Live document and section counts per area, from /sources (never hard-coded). */
export function CorpusSummary() {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    listSources()
      .then(setDocs)
      .catch(() => setFailed(true));
  }, []);

  const byArea = useMemo(() => {
    const out: Record<string, { docs: number; sections: number }> = {};
    for (const d of docs ?? []) {
      const a = (out[d.area] ??= { docs: 0, sections: 0 });
      a.docs += 1;
      a.sections += d.section_count;
    }
    return out;
  }, [docs]);

  if (failed) return <p className="text-muted-foreground">নথির তালিকা এখন আনা যাচ্ছে না।</p>;

  return (
    <div className="space-y-3">
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {AREAS.map((area) => {
          const Icon = area.icon;
          const stats = byArea[area.id];
          return (
            <li key={area.id} className="flex items-center gap-3 rounded-2xl border bg-card p-4 transition-shadow hover:shadow-card">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
                <Icon className="size-5" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="font-semibold leading-snug">{area.label}</p>
                {docs ? (
                  <p className="text-sm text-muted-foreground tabular-nums">
                    {toBnDigits(stats?.docs ?? 0)}টি নথি · {toBnDigits(stats?.sections ?? 0)}টি অংশ
                  </p>
                ) : (
                  <Skeleton className="mt-1 h-3.5 w-28" />
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <Link
        href="/sources"
        className="inline-flex items-center gap-1.5 font-medium text-primary underline-offset-4 hover:underline"
      >
        সব নথি দেখুন <ArrowRight className="size-4" aria-hidden />
      </Link>
    </div>
  );
}
