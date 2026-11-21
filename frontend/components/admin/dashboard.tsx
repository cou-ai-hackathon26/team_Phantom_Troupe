"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BarChart3, BookOpenText, Database, ExternalLink, FileStack, FileUp, Layers, LoaderCircle, LogOut, Upload } from "lucide-react";
import { EvalSection } from "@/components/eval-section";
import { Skeleton } from "@/components/ui/skeleton";
import { AREAS } from "@/lib/areas";
import { ApiError, adminJobs } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { AdminJob, AdminTotals } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DocumentsPanel } from "./documents-panel";
import type { AdminInfo } from "./shared";
import { JobCard, UploadForm } from "./upload-panel";

type Tab = "documents" | "upload" | "eval";

const TABS: { id: Tab; label: string; icon: typeof Database }[] = [
  { id: "documents", label: "নথিসমূহ", icon: Database },
  { id: "upload", label: "নতুন নথি", icon: Upload },
  { id: "eval", label: "মূল্যায়ন", icon: BarChart3 },
];

interface DashboardProps {
  token: string;
  info: AdminInfo | null;
  onLogout: () => void;
}

export function Dashboard({ token, info, onLogout }: DashboardProps) {
  const [tab, setTab] = useState<Tab>("documents");
  const [totals, setTotals] = useState<AdminTotals | null>(null);
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [version, setVersion] = useState(0); // bumped when an upload finishes: documents refetch
  const finished = useRef(new Set<string>());

  const loadJobs = useCallback(async () => {
    try {
      const list = await adminJobs(token);
      setJobs(list);
      // a job that just reached done/failed changes the document list
      let changed = false;
      for (const j of list) {
        if ((j.status === "done" || j.status === "failed") && !finished.current.has(j.id)) {
          finished.current.add(j.id);
          changed = true;
        }
      }
      if (changed) setVersion((v) => v + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onLogout();
    }
  }, [token, onLogout]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const active = jobs.filter((j) => j.status === "queued" || j.status === "running").length;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => void loadJobs(), 1500);
    return () => clearInterval(t);
  }, [active, loadJobs]);

  const maxChunks = Math.max(1, ...Object.values(totals?.chunks_by_area ?? {}));

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:py-10">
      {/* header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-primary">অ্যাডমিন প্যানেল</p>
          <h1 className="text-2xl font-bold sm:text-3xl">জ্ঞানভান্ডার</h1>
          {info?.email && (
            <p className="mt-0.5 text-sm text-muted-foreground">
              {/* the optional static ADMIN_TOKEN has no account; the backend reports it as "token" */}
              প্রবেশ করেছেন: {info.email === "token" ? "অ্যাডমিন টোকেন" : info.email}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/sources"
            className="inline-flex items-center gap-1.5 rounded-xl border bg-card px-3 py-2 text-sm font-medium transition-colors hover:border-primary/40 hover:text-primary"
          >
            <BookOpenText className="size-4" aria-hidden /> পাবলিক নথি-তালিকা <ExternalLink className="size-3" aria-hidden />
          </Link>
          <button
            type="button"
            onClick={onLogout}
            className="inline-flex items-center gap-1.5 rounded-xl border bg-card px-3 py-2 text-sm font-medium transition-colors hover:border-destructive/40 hover:text-destructive"
          >
            <LogOut className="size-4" aria-hidden /> বের হন
          </button>
        </div>
      </div>

      {/* stat tiles */}
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={FileStack} label="মোট নথি" value={totals?.docs} />
        <StatTile icon={Layers} label="নথি-অংশ (খোঁজার একক)" value={totals?.chunks} />
        <StatTile icon={FileUp} label="আপলোড করা নথি" value={totals?.uploaded} />
        <StatTile icon={LoaderCircle} label="চলমান আপলোড" value={totals ? active : undefined} spin={active > 0} />
      </ul>

      {/* coverage per area: one hue, labelled bars (identity is the label, not the colour) */}
      <section aria-labelledby="coverage-heading" className="rounded-2xl border bg-card p-4 sm:p-5">
        <h2 id="coverage-heading" className="font-semibold">
          বিষয়ভিত্তিক নথি
        </h2>
        <ul className="mt-3 grid gap-x-8 gap-y-3 sm:grid-cols-2">
          {AREAS.map((a) => {
            const chunks = totals?.chunks_by_area[a.id] ?? 0;
            const docs = totals?.docs_by_area[a.id] ?? 0;
            const Icon = a.icon;
            return (
              <li key={a.id} title={`${a.label}: ${docs} নথি, ${chunks} নথি-অংশ`}>
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-1.5 font-medium">
                    <Icon className="size-4 text-primary" aria-hidden /> {a.label}
                  </span>
                  {totals ? (
                    <span className="text-muted-foreground tabular-nums">
                      {toBnDigits(docs)}টি নথি · {toBnDigits(chunks)}টি অংশ
                    </span>
                  ) : (
                    <Skeleton className="h-3 w-24" />
                  )}
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-primary transition-[width] duration-700"
                    style={{ width: `${totals ? Math.max(chunks ? 2 : 0, (chunks / maxChunks) * 100) : 0}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {/* tabs */}
      <div role="tablist" aria-label="অ্যাডমিন বিভাগ" className="no-scrollbar flex gap-1 overflow-x-auto border-b">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            onClick={() => setTab(id)}
            className={cn(
              "-mb-px flex shrink-0 items-center gap-2 border-b-2 px-4 py-2.5 font-medium transition-colors",
              tab === id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
            {id === "upload" && active > 0 && (
              <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground tabular-nums">{toBnDigits(active)}</span>
            )}
          </button>
        ))}
      </div>

      <div id="panel-documents" role="tabpanel" hidden={tab !== "documents"}>
        <DocumentsPanel token={token} version={version} onTotals={setTotals} onUnauthorized={onLogout} />
      </div>

      <div id="panel-upload" role="tabpanel" hidden={tab !== "upload"} className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <UploadForm token={token} onStarted={() => void loadJobs()} />
        <section aria-labelledby="jobs-heading" className="space-y-3">
          <h2 id="jobs-heading" className="font-semibold">
            সাম্প্রতিক আপলোড
          </h2>
          {jobs.length === 0 ? (
            <p className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">
              এই সেশনে এখনো কোনো আপলোড হয়নি।
            </p>
          ) : (
            <ul className="space-y-2">
              {jobs.slice(0, 8).map((j) => (
                <JobCard key={j.id} job={j} token={token} />
              ))}
            </ul>
          )}
        </section>
      </div>

      <div id="panel-eval" role="tabpanel" hidden={tab !== "eval"} className="rounded-2xl border bg-card p-4 sm:p-6">
        {tab === "eval" && <EvalSection />}
      </div>

      {info && (
        <p className="text-xs text-muted-foreground">
          মডেল: {info.llm_model ?? "LLM_MODEL সেট করা নেই"} · এমবেডিং: {info.embedding_model}
        </p>
      )}
    </main>
  );
}

function StatTile({
  icon: Icon,
  label,
  value,
  spin,
}: {
  icon: typeof Database;
  label: string;
  value: number | undefined;
  spin?: boolean;
}) {
  return (
    <li className="rounded-2xl border bg-card p-4">
      <span className="flex size-9 items-center justify-center rounded-xl bg-primary-soft text-primary">
        <Icon className={cn("size-[1.1rem]", spin && "animate-spin motion-reduce:animate-none")} aria-hidden />
      </span>
      {value === undefined ? (
        <Skeleton className="mt-3 h-7 w-16" />
      ) : (
        <p className="mt-3 text-2xl font-bold tabular-nums sm:text-3xl">{toBnDigits(value.toLocaleString("en-US"))}</p>
      )}
      <p className="text-sm text-muted-foreground">{label}</p>
    </li>
  );
}
