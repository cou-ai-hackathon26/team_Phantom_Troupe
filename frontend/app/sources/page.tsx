"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ExternalLink, Search } from "lucide-react";
import { CitationSheet, type SourceView } from "@/components/chat/citation-sheet";
import { AREAS, areaLabel } from "@/lib/areas";
import { ApiError, getChunk, getDocument, listSources } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { DocumentDetail, DocumentSummary, SectionSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

function omit<T>(record: Record<string, T>, key: string): Record<string, T> {
  const copy = { ...record };
  delete copy[key];
  return copy;
}

export default function SourcesPage() {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [area, setArea] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, DocumentDetail | "loading">>({});
  const [source, setSource] = useState<SourceView | null>(null);

  useEffect(() => {
    listSources()
      .then(setDocs)
      .catch((e) => setError(e instanceof ApiError ? e.message : "নথির তালিকা আনা যায়নি।"));
  }, []);

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

  const q = query.trim();
  const filteredSections = (detail: DocumentDetail) =>
    q ? detail.sections.filter((s) => `${s.section} ${s.title}`.includes(q)) : detail.sections;

  const visible = useMemo(() => (docs ?? []).filter((d) => area === "all" || d.area === area), [docs, area]);

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">নথিসমূহ</h1>
        <p className="text-muted-foreground">যে সরকারি নথি থেকে অধিকারAI উত্তর দেয়। প্রতিটি ধারা খুলে মূল লেখা দেখতে পারেন।</p>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="বিষয় অনুযায়ী ছাঁকুন">
          {[{ id: "all", label: "সব" }, ...AREAS.map((a) => ({ id: a.id, label: a.label }))].map((opt) => (
            <button
              key={opt.id}
              type="button"
              aria-pressed={area === opt.id}
              onClick={() => setArea(opt.id)}
              className={cn(
                "rounded-full border px-3 py-1 text-[0.95rem]",
                area === opt.id ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-secondary",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <label className="relative block">
          <span className="sr-only">ধারা বা শিরোনাম খুঁজুন</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="ধারা নম্বর বা শিরোনাম লিখুন (যেমন: ছাঁটাই)"
            className="w-full rounded-xl border bg-card py-2.5 pr-3 pl-9 outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/25"
          />
        </label>
      </div>

      {error && <p className="rounded-xl border border-destructive/30 bg-card p-4" role="alert">{error}</p>}
      {!docs && !error && <p className="text-muted-foreground">লোড হচ্ছে…</p>}

      <ul className="space-y-3">
        {visible.map((doc) => {
          const detail = open[doc.document_id];
          return (
            <li key={doc.document_id} className="rounded-xl border bg-card">
              <button
                type="button"
                onClick={() => toggle(doc.document_id)}
                aria-expanded={Boolean(detail)}
                className="flex w-full items-start justify-between gap-3 p-4 text-left"
              >
                <span>
                  <span className="block text-sm text-primary">{areaLabel(doc.area)}</span>
                  <span className="block text-lg font-semibold">{doc.title}</span>
                  <span className="block text-sm text-muted-foreground">
                    {toBnDigits(doc.section_count)}টি অংশ · {doc.issuer}
                  </span>
                </span>
                <ChevronDown className={cn("mt-2 size-5 shrink-0 transition-transform", detail && "rotate-180")} aria-hidden />
              </button>
              {detail === "loading" && <p className="px-4 pb-4 text-muted-foreground">লোড হচ্ছে…</p>}
              {detail && detail !== "loading" && (
                <div className="border-t px-2 py-2">
                  <ul>
                    {filteredSections(detail).map((sec) => (
                      <li key={sec.section}>
                        <button
                          type="button"
                          onClick={() => void showSection(doc, sec)}
                          className="flex w-full gap-3 rounded-lg px-2 py-2 text-left hover:bg-secondary"
                        >
                          <span className="w-16 shrink-0 font-semibold text-primary">
                            {/^[০-৯]/.test(sec.section) ? `ধারা ${sec.section}` : sec.section}
                          </span>
                          <span>{sec.title}</span>
                        </button>
                      </li>
                    ))}
                    {filteredSections(detail).length === 0 && <li className="px-2 py-2 text-muted-foreground">কিছু পাওয়া যায়নি।</li>}
                  </ul>
                  {doc.source_url && (
                    <a
                      href={doc.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="m-2 inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
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
          <li className="rounded-xl border border-dashed p-6 text-center text-muted-foreground">
            এই বিষয়ের নথি এখনো যুক্ত হয়নি।
          </li>
        )}
      </ul>

      <CitationSheet source={source} onOpenChange={(o) => !o && setSource(null)} />
    </main>
  );
}
