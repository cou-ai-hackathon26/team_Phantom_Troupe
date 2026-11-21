"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpenText, ChevronDown, ExternalLink, LoaderCircle, Search, X } from "lucide-react";
import { CitationSheet, type SourceView } from "@/components/chat/citation-sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AREAS, areaLabel } from "@/lib/areas";
import { ApiError, getChunk, getDocument, listSources } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { DocumentDetail, DocumentSummary, SectionSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE = 30; // documents shown per "আরও দেখুন"

function omit<T>(record: Record<string, T>, key: string): Record<string, T> {
  const copy = { ...record };
  delete copy[key];
  return copy;
}

/** "গণপ্রজাতন্ত্রী বাংলাদেশের সংবিধান, অনুচ্ছেদ ২৭" -> "অনুচ্ছেদ ২৭"; falls back to the raw section. */
function sectionLabel(sec: SectionSummary): string {
  const tail = sec.citation.split(", ").at(-1) ?? "";
  if (tail && tail !== sec.citation) return tail;
  return /^[০-৯]/.test(sec.section) ? `ধারা ${sec.section}` : sec.section;
}

export default function SourcesPage() {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [area, setArea] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(PAGE);
  const [open, setOpen] = useState<Record<string, DocumentDetail | "loading">>({});
  const [source, setSource] = useState<SourceView | null>(null);

  useEffect(() => {
    listSources()
      .then(setDocs)
      .catch((e) => setError(e instanceof ApiError ? e.message : "নথির তালিকা আনা যায়নি।"));
  }, []);

  useEffect(() => setShown(PAGE), [area, query]);

  const toggle = (docId: string) => {
    if (open[docId]) {
      setOpen((o) => omit(o, docId));
      return;
    }
    setOpen((o) => ({ ...o, [docId]: "loading" }));
    getDocument(docId)
      .then((detail) => setOpen((o) => ({ ...o, [docId]: detail })))
      .catch(() => setOpen((o) => omit(o, docId)));
  };

  const showSection = async (doc: DocumentSummary, sec: SectionSummary) => {
    const base: SourceView = { citation: sec.citation, title: sec.title, text: "", notes: [], sourceUrl: null, loading: true };
    setSource(base);
    try {
      const parts = await Promise.all(sec.chunk_ids.map(getChunk));
      const text =
        parts.length === 1
          ? parts[0].text
          : parts.map((p, i) => `— অংশ ${toBnDigits(i + 1)}/${toBnDigits(parts.length)} —\n${p.text}`).join("\n\n");
      setSource({ ...base, text, notes: parts[0].notes, sourceUrl: parts[0].source_url ?? doc.source_url, loading: false });
    } catch {
      setSource({ ...base, text: "এই অংশটি আনা যায়নি।", loading: false });
    }
  };

  const q = query.trim().toLowerCase();
  const sectionMatches = (detail: DocumentDetail) =>
    q ? detail.sections.filter((s) => `${s.section} ${s.title} ${s.citation}`.toLowerCase().includes(q)) : detail.sections;

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: docs?.length ?? 0 };
    for (const d of docs ?? []) c[d.area] = (c[d.area] ?? 0) + 1;
    return c;
  }, [docs]);

  // a document matches by title or issuer; documents that are open stay visible to search inside them
  const visible = useMemo(
    () =>
      (docs ?? []).filter(
        (d) =>
          (area === "all" || d.area === area) &&
          (!q || `${d.title} ${d.issuer ?? ""}`.toLowerCase().includes(q) || Boolean(open[d.document_id])),
      ),
    [docs, area, q, open],
  );

  const filters = [{ id: "all", label: "সব" }, ...AREAS.map((a) => ({ id: a.id, label: a.label }))];

  return (
    <main className="mx-auto max-w-4xl px-4 py-6 sm:py-10">
      <div className="animate-fade-up space-y-2">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary-soft px-3 py-1 text-sm font-medium text-primary">
          <BookOpenText className="size-4" aria-hidden /> জ্ঞানভান্ডার
        </span>
        <h1 className="text-2xl font-bold sm:text-3xl">নথিসমূহ</h1>
        <p className="text-muted-foreground">
          যে সরকারি আইন ও নথি থেকে অধিকারAI উত্তর দেয়
          {docs ? ` (মোট ${toBnDigits(docs.length)}টি)` : ""}। নথি খুলে প্রতিটি ধারা বা অনুচ্ছেদের মূল লেখা দেখতে পারেন।
        </p>
      </div>

      <div className="glass sticky top-16 z-10 -mx-4 mt-5 space-y-3 border-b px-4 py-3 sm:mx-0 sm:rounded-2xl sm:border sm:px-4">
        <label className="relative block">
          <span className="sr-only">নথির নাম, ধারা বা শিরোনাম খুঁজুন</span>
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="নথির নাম বা ধারা খুঁজুন (যেমন: সংবিধান, ছাঁটাই)"
            className="w-full rounded-full border bg-card py-2.5 pr-10 pl-10 outline-none transition-shadow focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/10 [&::-webkit-search-cancel-button]:hidden"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              aria-label="খোঁজা মুছুন"
              className="absolute top-1/2 right-2 flex size-7 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary"
            >
              <X className="size-4" aria-hidden />
            </button>
          )}
        </label>
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label="বিষয় অনুযায়ী ছাঁকুন">
          {filters.map((opt) => (
            <button
              key={opt.id}
              type="button"
              aria-pressed={area === opt.id}
              onClick={() => setArea(opt.id)}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[0.93rem] transition-all",
                area === opt.id
                  ? "border-primary bg-primary font-medium text-primary-foreground shadow-card"
                  : "bg-card hover:border-primary/40 hover:bg-primary-soft",
              )}
            >
              {opt.label}
              {docs && (
                <span
                  className={cn(
                    "rounded-full px-1.5 text-xs tabular-nums",
                    area === opt.id ? "bg-primary-foreground/20" : "bg-secondary text-muted-foreground",
                  )}
                >
                  {toBnDigits(counts[opt.id] ?? 0)}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 space-y-3">
        {error && (
          <p className="rounded-2xl border border-destructive/30 bg-card p-4" role="alert">
            {error}
          </p>
        )}
        {!docs && !error && (
          <ul className="space-y-3" aria-label="লোড হচ্ছে">
            {[0, 1, 2, 3].map((i) => (
              <li key={i} className="space-y-2 rounded-2xl border bg-card p-4">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-3 w-1/3" />
              </li>
            ))}
          </ul>
        )}

        {docs && (
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {toBnDigits(visible.length)}টি নথি{q ? ` “${query.trim()}” মিলেছে` : ""}
          </p>
        )}

        <ul className="space-y-3">
          {visible.slice(0, shown).map((doc, i) => {
            const detail = open[doc.document_id];
            const sections = detail && detail !== "loading" ? sectionMatches(detail) : [];
            return (
              <li
                key={doc.document_id}
                className={cn(
                  "animate-fade-up overflow-hidden rounded-2xl border bg-card transition-shadow",
                  detail ? "shadow-card ring-1 ring-primary/15" : "hover:shadow-card",
                )}
                style={{ animationDelay: `${Math.min(i % PAGE, 10) * 30}ms` }}
              >
                <button
                  type="button"
                  onClick={() => toggle(doc.document_id)}
                  aria-expanded={Boolean(detail)}
                  className="flex w-full items-start justify-between gap-3 p-4 text-left"
                >
                  <span className="min-w-0">
                    <span className="mb-1 inline-block rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary">
                      {areaLabel(doc.area)}
                    </span>
                    <span className="block text-[1.05rem] leading-snug font-semibold break-words sm:text-lg">{doc.title}</span>
                    <span className="mt-0.5 block text-sm text-muted-foreground">
                      {toBnDigits(doc.section_count)}টি অংশ{doc.issuer ? ` · ${doc.issuer}` : ""}
                    </span>
                  </span>
                  <span
                    className={cn(
                      "mt-1 flex size-8 shrink-0 items-center justify-center rounded-full border transition-all",
                      detail && "rotate-180 border-primary/30 bg-primary-soft text-primary",
                    )}
                  >
                    {detail === "loading" ? (
                      <LoaderCircle className="size-4 animate-spin" aria-hidden />
                    ) : (
                      <ChevronDown className="size-4" aria-hidden />
                    )}
                  </span>
                </button>
                {detail && detail !== "loading" && (
                  <div className="animate-fade-up border-t bg-background/50 px-2 py-2">
                    <ul className="max-h-[26rem] overflow-y-auto">
                      {sections.map((sec) => (
                        <li key={`${sec.section}-${sec.chunk_ids[0]}`}>
                          <button
                            type="button"
                            onClick={() => void showSection(doc, sec)}
                            className="flex w-full items-baseline gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-primary-soft"
                          >
                            <span className="w-24 shrink-0 text-sm font-semibold text-primary sm:w-28">{sectionLabel(sec)}</span>
                            <span className="min-w-0 break-words">{sec.title}</span>
                          </button>
                        </li>
                      ))}
                      {sections.length === 0 && <li className="px-2 py-2 text-muted-foreground">কিছু পাওয়া যায়নি।</li>}
                    </ul>
                    {doc.source_url && (
                      <a
                        href={doc.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="m-2 inline-flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline"
                      >
                        মূল উৎস <ExternalLink className="size-3.5" aria-hidden />
                      </a>
                    )}
                  </div>
                )}
              </li>
            );
          })}
          {docs && visible.length === 0 && (
            <li className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">
              {q ? "এই নামে কোনো নথি পাওয়া যায়নি।" : "এই বিষয়ের নথি এখনো যুক্ত হয়নি।"}
            </li>
          )}
        </ul>

        {visible.length > shown && (
          <div className="flex flex-col items-center gap-1 pt-2">
            <button
              type="button"
              onClick={() => setShown((n) => n + PAGE)}
              className="rounded-full border bg-card px-6 py-2.5 font-medium shadow-card transition-all hover:border-primary/40 hover:text-primary active:scale-95"
            >
              আরও দেখুন
            </button>
            <span className="text-sm text-muted-foreground">
              {toBnDigits(shown)} / {toBnDigits(visible.length)}
            </span>
          </div>
        )}
      </div>

      <CitationSheet source={source} onOpenChange={(o) => !o && setSource(null)} />
    </main>
  );
}
