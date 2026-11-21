"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, ExternalLink, Eye, LoaderCircle, LockKeyhole, LogOut, Trash2, Upload, XCircle } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { AREAS, areaLabel } from "@/lib/areas";
import {
  ApiError,
  adminCheck,
  adminLogin,
  adminDelete,
  adminDocument,
  adminDocuments,
  adminJob,
  adminJobs,
  adminUpload,
} from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { AdminDocument, AdminJob, AdminSection } from "@/lib/types";
import { cn } from "@/lib/utils";

const TOKEN_KEY = "adhikarai.adminToken";

function readToken(): string {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveToken(token: string | null) {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the admin signs in again after a reload */
  }
}

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "কিছু একটা সমস্যা হয়েছে।");

export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null);
  const [info, setInfo] = useState<AdminInfo | null>(null);

  useEffect(() => {
    const saved = readToken();
    if (!saved) return;
    adminCheck(saved)
      .then((res) => {
        setToken(saved);
        setInfo(res);
      })
      .catch(() => saveToken(null));
  }, []);

  if (!token) {
    return (
      <Login
        onLogin={(t, res) => {
          saveToken(t);
          setToken(t);
          setInfo(res);
        }}
      />
    );
  }
  return (
    <Dashboard
      token={token}
      info={info}
      onLogout={() => {
        saveToken(null);
        setToken(null);
      }}
    />
  );
}

type AdminInfo = { email: string; llm_model: string | null; embedding_model: string };

function Login({ onLogin }: { onLogin: (token: string, info: AdminInfo) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const field =
    "w-full rounded-xl border bg-background px-3 py-2.5 outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/25";
  return (
    <main className="mx-auto max-w-md px-4 py-16">
      <form
        className="space-y-4 rounded-xl border bg-card p-6"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const session = await adminLogin(email.trim(), password);
            onLogin(session.token, await adminCheck(session.token));
          } catch (err) {
            setError(errorText(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="flex items-center gap-2">
          <LockKeyhole className="size-5 text-primary" aria-hidden />
          <h1 className="text-xl font-semibold">অ্যাডমিন লগইন</h1>
        </div>
        <p className="text-sm text-muted-foreground">জ্ঞানভান্ডারের নথি দেখা, যোগ ও মোছার জন্য অ্যাডমিন অ্যাকাউন্টে প্রবেশ করুন।</p>
        <label className="block space-y-1">
          <span className="text-sm font-semibold">ইমেইল</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} className={field} />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-semibold">পাসওয়ার্ড</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={field}
          />
        </label>
        {error && (
          <p className="text-sm text-destructive" role="alert" data-testid="login-error">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={!email.trim() || !password || busy}
          className="w-full rounded-xl bg-primary px-4 py-2.5 font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {busy ? "যাচাই হচ্ছে…" : "লগইন"}
        </button>
      </form>
    </main>
  );
}

function Dashboard({
  token,
  info,
  onLogout,
}: {
  token: string;
  info: AdminInfo | null;
  onLogout: () => void;
}) {
  const [docs, setDocs] = useState<AdminDocument[] | null>(null);
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{ doc: AdminDocument; sections: AdminSection[] | null } | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [d, j] = await Promise.all([adminDocuments(token), adminJobs(token)]);
      setDocs(d);
      setJobs(j);
      setError(null);
    } catch (err) {
      setError(errorText(err));
      if (err instanceof ApiError && err.status === 401) onLogout();
    }
  }, [token, onLogout]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // poll while a job runs
  const active = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => void refresh(), 1500);
    return () => clearInterval(t);
  }, [active, refresh]);

  const totals = useMemo(() => {
    const byArea: Record<string, number> = {};
    for (const d of docs ?? []) byArea[d.area] = (byArea[d.area] ?? 0) + d.chunks;
    return { docs: docs?.length ?? 0, chunks: (docs ?? []).reduce((n, d) => n + d.chunks, 0), byArea };
  }, [docs]);

  const view = async (doc: AdminDocument) => {
    setViewing({ doc, sections: null });
    try {
      const res = await adminDocument(token, doc.document_id);
      setViewing({ doc, sections: res.sections });
    } catch (err) {
      setError(errorText(err));
      setViewing(null);
    }
  };

  const remove = async (doc: AdminDocument) => {
    if (!window.confirm(`“${doc.title}” জ্ঞানভান্ডার থেকে মুছে ফেলবেন? এই নথি থেকে আর উত্তর দেওয়া হবে না।`)) return;
    setDeleting(doc.document_id);
    try {
      await adminDelete(token, doc.document_id);
      await refresh();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setDeleting(null);
    }
  };

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">অ্যাডমিন প্যানেল</h1>
          <p className="text-sm text-muted-foreground">
            {info?.email && <span className="font-semibold text-foreground">{info.email} · </span>}
            জ্ঞানভান্ডার: {toBnDigits(totals.docs)}টি নথি, {toBnDigits(totals.chunks)}টি নথি-অংশ
            {info && ` · মডেল: ${info.llm_model ?? "LLM_MODEL সেট করা নেই"} · এমবেডিং: ${info.embedding_model}`}
          </p>
        </div>
        <button type="button" onClick={onLogout} className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm hover:bg-secondary">
          <LogOut className="size-4" aria-hidden /> বের হন
        </button>
      </div>

      {error && (
        <p className="rounded-xl border border-destructive/30 bg-card p-3 text-destructive" role="alert">
          {error}
        </p>
      )}

      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {AREAS.map((a) => {
          const Icon = a.icon;
          const n = totals.byArea[a.id] ?? 0;
          return (
            <li key={a.id} className={cn("rounded-xl border bg-card p-3", n === 0 && "border-dashed")}>
              <Icon className="size-4 text-primary" aria-hidden />
              <p className="mt-1 font-semibold">{a.label}</p>
              <p className="text-sm text-muted-foreground">{n ? `${toBnDigits(n)}টি নথি-অংশ` : "নথি নেই"}</p>
            </li>
          );
        })}
      </ul>

      <UploadForm token={token} onStarted={() => void refresh()} />

      {jobs.length > 0 && (
        <section aria-labelledby="jobs-heading" className="space-y-2">
          <h2 id="jobs-heading" className="text-lg font-semibold">সাম্প্রতিক আপলোড</h2>
          <ul className="space-y-2">
            {jobs.slice(0, 5).map((j) => (
              <JobCard key={j.id} job={j} token={token} />
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="docs-heading" className="space-y-2">
        <h2 id="docs-heading" className="text-lg font-semibold">জ্ঞানভান্ডারের নথি</h2>
        {!docs && !error && <p className="text-muted-foreground">লোড হচ্ছে…</p>}
        <ul className="space-y-2">
          {(docs ?? []).map((d) => (
            <li key={d.document_id} className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="rounded-full bg-primary-soft px-2 py-0.5 text-primary">{areaLabel(d.area)}</span>
                  {d.builtin && <span className="rounded-full bg-secondary px-2 py-0.5 text-muted-foreground">প্রকল্পের অংশ</span>}
                  <code className="text-xs text-muted-foreground">{d.document_id}</code>
                </p>
                <p className="mt-1 text-lg font-semibold">{d.title}</p>
                <p className="text-sm text-muted-foreground">
                  {toBnDigits(d.sections)}টি অংশ · {toBnDigits(d.chunks)}টি নথি-অংশ{d.issuer ? ` · ${d.issuer}` : ""}
                </p>
                {d.source_url && (
                  <a href={d.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                    উৎস <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                )}
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => void view(d)} className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm hover:bg-secondary">
                  <Eye className="size-4" aria-hidden /> দেখুন
                </button>
                <button
                  type="button"
                  onClick={() => void remove(d)}
                  disabled={d.builtin || deleting === d.document_id}
                  title={d.builtin ? "প্রকল্পের অংশ — এখান থেকে মোছা যায় না" : "জ্ঞানভান্ডার থেকে মুছুন"}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/30 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/5 disabled:opacity-40"
                >
                  {deleting === d.document_id ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Trash2 className="size-4" aria-hidden />} মুছুন
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <Sheet open={viewing !== null} onOpenChange={(o) => !o && setViewing(null)}>
        <SheetContent side="right" className="w-full gap-0 sm:max-w-2xl">
          {viewing && (
            <>
              <SheetHeader className="border-b pr-12">
                <SheetTitle className="text-lg">{viewing.doc.title}</SheetTitle>
                <SheetDescription>
                  {areaLabel(viewing.doc.area)} · {toBnDigits(viewing.doc.sections)}টি অংশ · {toBnDigits(viewing.doc.chunks)}টি নথি-অংশ
                </SheetDescription>
              </SheetHeader>
              <div className="flex-1 space-y-3 overflow-y-auto p-4">
                {!viewing.sections && <p className="text-muted-foreground">লোড হচ্ছে…</p>}
                {viewing.sections?.map((s) => (
                  <details key={s.id} className="rounded-lg border p-3">
                    <summary className="cursor-pointer">
                      <span className="font-semibold">{/^[০-৯]/.test(s.section) ? `ধারা ${s.section}` : s.section}</span> — {s.title}
                      <span className="block text-xs text-muted-foreground">
                        {s.source_file} · {toBnDigits(s.chars)} অক্ষর{s.notes ? ` · ${toBnDigits(s.notes)}টি সংশোধনী টীকা` : ""}
                      </span>
                    </summary>
                    <p className="mt-2 whitespace-pre-line text-[0.95rem] leading-[1.8]">{s.text}</p>
                  </details>
                ))}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </main>
  );
}

function UploadForm({ token, onStarted }: { token: string; onStarted: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [area, setArea] = useState("land");
  const [title, setTitle] = useState("");
  const [issuer, setIssuer] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [parser, setParser] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputKey, setInputKey] = useState(0);

  const submit = async () => {
    if (!file || title.trim().length < 2) return;
    setBusy(true);
    setError(null);
    try {
      await adminUpload(token, file, { area, title: title.trim(), issuer: issuer.trim(), source_url: sourceUrl.trim(), parser });
      setFile(null);
      setTitle("");
      setIssuer("");
      setSourceUrl("");
      setInputKey((k) => k + 1);
      onStarted();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const field = "w-full rounded-xl border bg-background px-3 py-2 outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/25";
  return (
    <section aria-labelledby="upload-heading" className="space-y-4 rounded-xl border bg-card p-4 sm:p-5">
      <div>
        <h2 id="upload-heading" className="flex items-center gap-2 text-lg font-semibold">
          <Upload className="size-5 text-primary" aria-hidden /> নতুন নথি যোগ করুন
        </h2>
        <p className="text-sm text-muted-foreground">
          শুধু সরকারি নথি দিন। PDF (লেখা, পুরনো বিজয় ফন্ট বা স্ক্যান) অথবা ছবি। স্ক্যান করা পাতায় স্বয়ংক্রিয়ভাবে OCR হবে। যোগ হওয়ার পর থেকেই এই নথি থেকে উত্তর দেওয়া হবে।
        </p>
      </div>
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label className="space-y-1 sm:col-span-2">
          <span className="text-sm font-semibold">ফাইল *</span>
          <input
            key={inputKey}
            type="file"
            required
            accept="application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-primary-soft file:px-3 file:py-2 file:font-semibold file:text-primary"
          />
        </label>
        <label className="space-y-1">
          <span className="text-sm font-semibold">বিষয় *</span>
          <select value={area} onChange={(e) => setArea(e.target.value)} className={field}>
            {AREAS.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-sm font-semibold">পার্সার</span>
          <select value={parser} onChange={(e) => setParser(e.target.value)} className={field}>
            <option value="auto">স্বয়ংক্রিয় (bdlaws হলে ধারা অনুযায়ী)</option>
            <option value="bdlaws">bdlaws.minlaw.gov.bd প্রিন্ট PDF</option>
            <option value="generic">সাধারণ (পৃষ্ঠা অনুযায়ী, OCR সহ)</option>
          </select>
        </label>
        <label className="space-y-1 sm:col-span-2">
          <span className="text-sm font-semibold">নথির সরকারি নাম *</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} required minLength={2} placeholder="যেমন: বয়স্ক ভাতা কর্মসূচি বাস্তবায়ন নীতিমালা" className={field} />
        </label>
        <label className="space-y-1">
          <span className="text-sm font-semibold">প্রকাশকারী দপ্তর</span>
          <input value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="যেমন: সমাজসেবা অধিদফতর" className={field} />
        </label>
        <label className="space-y-1">
          <span className="text-sm font-semibold">সরকারি উৎসের লিংক</span>
          <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} type="url" placeholder="https://…gov.bd/…" className={field} />
        </label>
        {error && (
          <p className="text-sm text-destructive sm:col-span-2" role="alert">
            {error}
          </p>
        )}
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={!file || title.trim().length < 2 || busy}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {busy ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <Upload className="size-4" aria-hidden />}
            আপলোড ও জ্ঞানভান্ডারে যোগ
          </button>
        </div>
      </form>
    </section>
  );
}

const JOB_STATUS: Record<AdminJob["status"], string> = {
  queued: "অপেক্ষমাণ",
  running: "চলছে",
  done: "সম্পন্ন",
  failed: "ব্যর্থ",
};

function JobCard({ job: initial, token }: { job: AdminJob; token: string }) {
  const [job, setJob] = useState(initial);
  useEffect(() => setJob(initial), [initial]);
  useEffect(() => {
    if (job.status === "done" || job.status === "failed") return;
    const t = setInterval(() => {
      adminJob(token, job.id).then(setJob).catch(() => undefined);
    }, 1200);
    return () => clearInterval(t);
  }, [job.id, job.status, token]);

  return (
    <li className="rounded-xl border bg-card p-3">
      <div className="flex items-center gap-2">
        {job.status === "done" ? (
          <CheckCircle2 className="size-4 text-status-answered" aria-hidden />
        ) : job.status === "failed" ? (
          <XCircle className="size-4 text-destructive" aria-hidden />
        ) : (
          <LoaderCircle className="size-4 animate-spin text-primary motion-reduce:animate-none" aria-hidden />
        )}
        <p className="min-w-0 flex-1 truncate">
          <span className="font-semibold">{job.title}</span> <span className="text-sm text-muted-foreground">({job.filename})</span>
        </p>
        <span className="text-sm text-muted-foreground">{JOB_STATUS[job.status]}</span>
      </div>
      {job.status === "done" && (
        <p className="mt-1 text-sm text-muted-foreground">
          {toBnDigits(job.sections)}টি অংশ, {toBnDigits(job.chunks)}টি নথি-অংশ যোগ হয়েছে{job.needs_review && " · কিছু পাতা অস্পষ্ট, যাচাই করুন"}
        </p>
      )}
      {job.error && <p className="mt-1 text-sm text-destructive">{job.error}</p>}
      <details className="mt-1">
        <summary className="cursor-pointer text-xs text-muted-foreground">বিস্তারিত ধাপ</summary>
        <ol className="mt-1 list-decimal space-y-0.5 pl-5 font-mono text-xs text-muted-foreground">
          {job.steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </details>
    </li>
  );
}
