"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Eye, FileText, LoaderCircle, Search, Trash2, X } from "lucide-react";
import { Pagination } from "@/components/ui/pagination";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { AREAS, areaLabel } from "@/lib/areas";
import { ApiError, adminDelete, adminDocument, adminDocuments, type AdminDocKind } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { AdminDocument, AdminDocumentDetail, AdminDocumentPage, AdminTotals } from "@/lib/types";
import { cn } from "@/lib/utils";
import { errorText } from "./shared";

const PAGE_SIZE = 15;
const SECTION_PAGE_SIZE = 20;

const KINDS: { id: AdminDocKind; label: string }[] = [
  { id: "all", label: "সব" },
  { id: "uploaded", label: "আপলোড করা" },
  { id: "builtin", label: "প্রকল্পের অংশ" },
];

interface DocumentsPanelProps {
  token: string;
  version: number; // bumped after an upload finishes, to refetch
  onTotals: (totals: AdminTotals) => void;
  onUnauthorized: () => void;
}

export function DocumentsPanel({ token, version, onTotals, onUnauthorized }: DocumentsPanelProps) {
  const [query, setQuery] = useState("");
  const [area, setArea] = useState("all");
  const [kind, setKind] = useState<AdminDocKind>("all");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AdminDocumentPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [viewing, setViewing] = useState<AdminDocument | null>(null);
  const [reload, setReload] = useState(0);
  const q = useDebouncedValue(query.trim(), 300);

  useEffect(() => setPage(1), [q, area, kind]);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    adminDocuments(token, { q, area: area === "all" ? undefined : area, kind, page, pageSize: PAGE_SIZE }, { signal: ctrl.signal })
      .then((res) => {
        setData(res);
        onTotals(res.totals);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        if (ctrl.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401) onUnauthorized();
        setError(errorText(err));
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [token, q, area, kind, page, version, reload, onTotals, onUnauthorized]);

  const remove = async (doc: AdminDocument) => {
    if (!window.confirm(`“${doc.title}” জ্ঞানভান্ডার থেকে মুছে ফেলবেন? এই নথি থেকে আর উত্তর দেওয়া হবে না।`)) return;
    setDeleting(doc.document_id);
    try {
      await adminDelete(token, doc.document_id);
      setReload((n) => n + 1);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setDeleting(null);
    }
  };

  const chip = (active: boolean) =>
    cn(
      "shrink-0 rounded-full border px-3 py-1.5 text-sm transition-all",
      active ? "border-primary bg-primary font-medium text-primary-foreground" : "bg-card hover:border-primary/40 hover:bg-primary-soft",
    );

  return (
    <section aria-label="জ্ঞানভান্ডারের নথি" className="space-y-4">
      <div className="space-y-3 rounded-2xl border bg-card p-3 sm:p-4">
        <label className="relative block">
          <span className="sr-only">নথি খুঁজুন</span>
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="নাম, দপ্তর বা আইডি দিয়ে খুঁজুন"
            className="w-full rounded-xl border bg-background py-2.5 pr-10 pl-10 outline-none focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/10 [&::-webkit-search-cancel-button]:hidden"
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
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="no-scrollbar -mx-3 flex gap-2 overflow-x-auto px-3 sm:mx-0 sm:px-0" role="group" aria-label="বিষয়">
            {[{ id: "all", label: "সব বিষয়" }, ...AREAS.map((a) => ({ id: a.id, label: a.label }))].map((o) => (
              <button key={o.id} type="button" aria-pressed={area === o.id} onClick={() => setArea(o.id)} className={chip(area === o.id)}>
                {o.label}
              </button>
            ))}
          </div>
          <div className="flex shrink-0 rounded-full border bg-background p-0.5 text-sm" role="radiogroup" aria-label="ধরন">
            {KINDS.map((k) => (
              <button
                key={k.id}
                type="button"
                role="radio"
                aria-checked={kind === k.id}
                onClick={() => setKind(k.id)}
                className={cn(
                  "flex-1 rounded-full px-3 py-1 whitespace-nowrap transition-colors",
                  kind === k.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {k.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <p className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-destructive" role="alert">
          {error}
        </p>
      )}

      {!data && !error && (
        <ul className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <li key={i} className="space-y-2 rounded-2xl border bg-card p-4">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </li>
          ))}
        </ul>
      )}

      {data && (
        <>
          <ul className={cn("space-y-2 transition-opacity", loading && "opacity-60")} aria-busy={loading}>
            {data.items.map((d) => (
              <li
                key={d.document_id}
                className="group flex flex-col gap-3 rounded-2xl border bg-card p-4 transition-shadow hover:shadow-card sm:flex-row sm:items-center"
              >
                <span className="hidden size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary sm:flex">
                  <FileText className="size-5" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="rounded-full bg-primary-soft px-2 py-0.5 font-medium text-primary">{areaLabel(d.area)}</span>
                    {d.builtin ? (
                      <span className="rounded-full bg-secondary px-2 py-0.5 text-muted-foreground">প্রকল্পের অংশ</span>
                    ) : (
                      <span className="rounded-full bg-status-clarify-bg px-2 py-0.5 text-status-clarify">আপলোড করা</span>
                    )}
                  </p>
                  <p className="mt-1 font-semibold leading-snug break-words sm:text-[1.05rem]">{d.title}</p>
                  <p className="mt-0.5 text-sm text-muted-foreground">
                    {toBnDigits(d.sections)}টি অংশ · {toBnDigits(d.chunks)}টি নথি-অংশ{d.issuer ? ` · ${d.issuer}` : ""}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                    <code className="truncate">{d.document_id}</code>
                    {d.source_url && (
                      <a
                        href={d.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        উৎস <ExternalLink className="size-3" aria-hidden />
                      </a>
                    )}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setViewing(d)}
                    className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors hover:border-primary/40 hover:text-primary sm:flex-none"
                  >
                    <Eye className="size-4" aria-hidden /> দেখুন
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(d)}
                    disabled={d.builtin || deleting === d.document_id}
                    title={d.builtin ? "প্রকল্পের অংশ — এখান থেকে মোছা যায় না" : "জ্ঞানভান্ডার থেকে মুছুন"}
                    className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-destructive/30 px-3 py-2 text-sm font-medium text-destructive transition-colors hover:bg-destructive/5 disabled:opacity-40 sm:flex-none"
                  >
                    {deleting === d.document_id ? (
                      <LoaderCircle className="size-4 animate-spin" aria-hidden />
                    ) : (
                      <Trash2 className="size-4" aria-hidden />
                    )}
                    মুছুন
                  </button>
                </div>
              </li>
            ))}
            {data.items.length === 0 && (
              <li className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">কোনো নথি পাওয়া যায়নি।</li>
            )}
          </ul>
          <Pagination
            page={data.page}
            pages={data.pages}
            total={data.total}
            pageSize={data.page_size}
            onPage={setPage}
            disabled={loading}
            unit="টি নথি"
          />
        </>
      )}

      <DocumentSheet token={token} doc={viewing} onClose={() => setViewing(null)} />
    </section>
  );
}

/** A document's sections, fetched one page at a time (large acts have hundreds of sections). */
function DocumentSheet({ token, doc, onClose }: { token: string; doc: AdminDocument | null; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<AdminDocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const q = useDebouncedValue(query.trim(), 300);
  const docId = doc?.document_id;

  useEffect(() => {
    setPage(1);
    setQuery("");
    setData(null);
  }, [docId]);
  useEffect(() => setPage(1), [q]);

  useEffect(() => {
    if (!docId) return;
    let cancelled = false;
    setLoading(true);
    adminDocument(token, docId, { q, page, pageSize: SECTION_PAGE_SIZE })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => !cancelled && setError(errorText(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [token, docId, q, page]);

  return (
    <Sheet open={doc !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-2xl">
        {doc && (
          <>
            <SheetHeader className="border-b pr-12">
              <SheetTitle className="text-lg leading-snug">{doc.title}</SheetTitle>
              <SheetDescription>
                {areaLabel(doc.area)} · {toBnDigits(doc.sections)}টি অংশ · {toBnDigits(doc.chunks)}টি নথি-অংশ
              </SheetDescription>
              <label className="relative mt-2 block">
                <span className="sr-only">অংশ খুঁজুন</span>
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="ধারা নম্বর বা শিরোনাম"
                  className="w-full rounded-xl border bg-background py-2 pr-3 pl-9 text-sm outline-none focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/10"
                />
              </label>
            </SheetHeader>
            <div className={cn("flex-1 space-y-2 overflow-y-auto p-4 transition-opacity", loading && data && "opacity-60")}>
              {error && <p className="text-destructive">{error}</p>}
              {!data && !error && (
                <div className="space-y-2">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-14 w-full rounded-xl" />
                  ))}
                </div>
              )}
              {data?.sections.map((s) => (
                <details key={s.id} className="group rounded-xl border bg-card p-3 open:shadow-card">
                  <summary className="cursor-pointer list-none">
                    <span className="font-semibold text-primary">{s.citation.split(", ").at(-1) || s.section}</span>
                    <span> — {s.title}</span>
                    <span className="block text-xs text-muted-foreground">
                      {s.source_file} · {toBnDigits(s.chars)} অক্ষর{s.notes ? ` · ${toBnDigits(s.notes)}টি সংশোধনী টীকা` : ""}
                    </span>
                  </summary>
                  <p className="mt-2 border-t pt-2 text-[0.95rem] leading-[1.8] whitespace-pre-line">{s.text}</p>
                </details>
              ))}
              {data && data.sections.length === 0 && <p className="text-muted-foreground">কিছু পাওয়া যায়নি।</p>}
            </div>
            {data && data.pages > 1 && (
              <div className="border-t p-3">
                <Pagination
                  page={data.page}
                  pages={data.pages}
                  total={data.total}
                  pageSize={data.page_size}
                  onPage={setPage}
                  disabled={loading}
                  unit="টি অংশ"
                />
              </div>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
