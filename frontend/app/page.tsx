"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getHealth } from "@/lib/api";
import type { HealthReport } from "@/lib/types";

// Phase 1 placeholder: service status. Replaced by the chat UI in Phase 5.
export default function Home() {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setReport(await getHealth());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="mx-auto max-w-xl px-4 py-12">
      <h1 className="text-3xl font-semibold text-primary">অধিকারAI</h1>
      <p className="mt-1 text-muted-foreground">সার্ভিস অবস্থা</p>

      <div className="mt-8 rounded-xl border bg-card p-5" aria-live="polite">
        {error && <p className="text-destructive">ব্যাকএন্ডের সাথে সংযোগ হয়নি। সার্ভার চালু আছে কি না দেখুন।</p>}
        {loading && !report && <p className="text-muted-foreground">যাচাই করছি…</p>}
        {report && (
          <ul className="space-y-3">
            {Object.entries(report.services).map(([name, s]) => (
              <li key={name} className="flex items-start gap-3">
                {s.ok ? (
                  <CheckCircle2 className="mt-1 size-5 text-status-answered" aria-label="ঠিক আছে" />
                ) : (
                  <XCircle className="mt-1 size-5 text-destructive" aria-label="সমস্যা" />
                )}
                <div>
                  <p className="font-semibold">{name}</p>
                  <p className="text-sm text-muted-foreground break-all">{s.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Button className="mt-4" variant="outline" onClick={() => void load()} disabled={loading}>
        <RefreshCw className="size-4" aria-hidden /> আবার যাচাই করুন
      </Button>
    </main>
  );
}
