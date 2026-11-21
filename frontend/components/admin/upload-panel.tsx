"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";
import { CheckCircle2, CloudUpload, FileText, LoaderCircle, Upload, X, XCircle } from "lucide-react";
import { AREAS, areaLabel } from "@/lib/areas";
import { adminJob, adminUpload } from "@/lib/api";
import { toBnDigits } from "@/lib/bn";
import type { AdminJob } from "@/lib/types";
import { cn } from "@/lib/utils";
import { errorText, fieldClass } from "./shared";

const ACCEPT = "application/pdf,image/png,image/jpeg,image/webp,.pdf,.png,.jpg,.jpeg,.webp";

function sizeLabel(bytes: number): string {
  return bytes < 1024 * 1024 ? `${toBnDigits(Math.max(1, Math.round(bytes / 1024)))} KB` : `${toBnDigits((bytes / 1024 / 1024).toFixed(1))} MB`;
}

export function UploadForm({ token, onStarted }: { token: string; onStarted: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [area, setArea] = useState("land");
  const [title, setTitle] = useState("");
  const [issuer, setIssuer] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [parser, setParser] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

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
      onStarted();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e: DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  };

  return (
    <section aria-labelledby="upload-heading" className="rounded-2xl border bg-card p-4 shadow-card sm:p-6">
      <h2 id="upload-heading" className="text-lg font-semibold">
        নতুন নথি যোগ করুন
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        শুধু সরকারি নথি দিন: PDF (লেখা, পুরনো বিজয় ফন্ট বা স্ক্যান) অথবা ছবি। স্ক্যান করা পাতায় স্বয়ংক্রিয়ভাবে OCR হবে।
      </p>

      <form
        className="mt-5 grid gap-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            e.target.value = "";
          }}
        />
        {file ? (
          <div className="flex items-center gap-3 rounded-2xl border border-primary/30 bg-primary-soft/60 p-4 sm:col-span-2">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <FileText className="size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{file.name}</p>
              <p className="text-sm text-muted-foreground">{sizeLabel(file.size)}</p>
            </div>
            <button
              type="button"
              onClick={() => setFile(null)}
              aria-label="ফাইল সরান"
              className="flex size-9 items-center justify-center rounded-full text-muted-foreground hover:bg-background hover:text-foreground"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-8 text-center transition-colors sm:col-span-2",
              dragging ? "border-primary bg-primary-soft" : "hover:border-primary/50 hover:bg-primary-soft/40",
            )}
          >
            <span className="flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
              <CloudUpload className="size-6" aria-hidden />
            </span>
            <span className="font-semibold">ফাইল টেনে এনে ছাড়ুন, অথবা চাপ দিয়ে বেছে নিন</span>
            <span className="text-sm text-muted-foreground">PDF, PNG, JPG বা WEBP</span>
          </button>
        )}

        <label className="space-y-1.5 sm:col-span-2">
          <span className="text-sm font-semibold">নথির সরকারি নাম *</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            minLength={2}
            placeholder="যেমন: বয়স্ক ভাতা কর্মসূচি বাস্তবায়ন নীতিমালা"
            className={fieldClass}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-semibold">বিষয় *</span>
          <select value={area} onChange={(e) => setArea(e.target.value)} className={fieldClass}>
            {AREAS.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-semibold">পার্সার</span>
          <select value={parser} onChange={(e) => setParser(e.target.value)} className={fieldClass}>
            <option value="auto">স্বয়ংক্রিয় (bdlaws হলে ধারা অনুযায়ী)</option>
            <option value="bdlaws">bdlaws.minlaw.gov.bd প্রিন্ট PDF</option>
            <option value="generic">সাধারণ (পৃষ্ঠা অনুযায়ী, OCR সহ)</option>
          </select>
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-semibold">প্রকাশকারী দপ্তর</span>
          <input value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="যেমন: সমাজসেবা অধিদফতর" className={fieldClass} />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-semibold">সরকারি উৎসের লিংক</span>
          <input
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            type="url"
            placeholder="https://…gov.bd/…"
            className={fieldClass}
          />
        </label>
        {error && (
          <p className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive sm:col-span-2" role="alert">
            {error}
          </p>
        )}
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={!file || title.trim().length < 2 || busy}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3 font-semibold text-primary-foreground shadow-card transition-all hover:bg-primary/90 active:scale-[0.98] disabled:opacity-60 sm:w-auto"
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

export function JobCard({ job: initial, token }: { job: AdminJob; token: string }) {
  const [job, setJob] = useState(initial);
  useEffect(() => setJob(initial), [initial]);
  useEffect(() => {
    if (job.status === "done" || job.status === "failed") return;
    const t = setInterval(() => {
      adminJob(token, job.id).then(setJob).catch(() => undefined);
    }, 1200);
    return () => clearInterval(t);
  }, [job.id, job.status, token]);

  const running = job.status === "queued" || job.status === "running";
  return (
    <li className="rounded-2xl border bg-card p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-xl",
            job.status === "done" && "bg-status-answered-bg text-status-answered",
            job.status === "failed" && "bg-destructive/10 text-destructive",
            running && "bg-primary-soft text-primary",
          )}
        >
          {job.status === "done" ? (
            <CheckCircle2 className="size-5" aria-hidden />
          ) : job.status === "failed" ? (
            <XCircle className="size-5" aria-hidden />
          ) : (
            <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{job.title}</p>
          <p className="truncate text-sm text-muted-foreground">
            {job.filename} · {areaLabel(job.area)}
          </p>
        </div>
        <span className="shrink-0 rounded-full border px-2.5 py-0.5 text-xs">{JOB_STATUS[job.status]}</span>
      </div>
      {running && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-secondary" aria-hidden>
          <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
        </div>
      )}
      {running && job.steps.length > 0 && <p className="mt-2 text-sm text-muted-foreground">{job.steps[job.steps.length - 1]}</p>}
      {job.status === "done" && (
        <p className="mt-2 text-sm text-muted-foreground">
          {toBnDigits(job.sections)}টি অংশ, {toBnDigits(job.chunks)}টি নথি-অংশ যোগ হয়েছে
          {job.needs_review && " · কিছু পাতা অস্পষ্ট, যাচাই করুন"}
        </p>
      )}
      {job.error && <p className="mt-2 text-sm text-destructive">{job.error}</p>}
      {job.steps.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-muted-foreground">বিস্তারিত ধাপ</summary>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 font-mono text-xs text-muted-foreground">
            {job.steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </details>
      )}
    </li>
  );
}
