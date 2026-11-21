"use client";

import { useState } from "react";
import { Eye, EyeOff, FileUp, LoaderCircle, LockKeyhole, Mail, ShieldCheck, TriangleAlert, Trash2 } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { adminCheck, adminLogin } from "@/lib/api";
import { cn } from "@/lib/utils";
import { errorText, type AdminInfo } from "./shared";

const POINTS = [
  { icon: FileUp, text: "সরকারি নথি আপলোড করে জ্ঞানভান্ডারে যোগ" },
  { icon: ShieldCheck, text: "প্রতিটি নথির ধারা ও লেখা যাচাই" },
  { icon: Trash2, text: "পুরনো বা ভুল নথি সরিয়ে ফেলা" },
];

export function LoginForm({ onLogin }: { onLogin: (token: string, info: AdminInfo) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
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
  };

  const input =
    "w-full rounded-xl border bg-background py-3 pr-3.5 pl-10 outline-none transition-shadow placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/10";

  return (
    <main className="flex min-h-[calc(100dvh-4rem)] items-center justify-center px-4 py-10">
      <div className="grid w-full max-w-4xl animate-fade-up overflow-hidden rounded-3xl border bg-card shadow-card md:grid-cols-[1fr_1.1fr]">
        {/* brand panel */}
        <div className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-[#0f8a63] to-[#06402e] p-8 text-white md:flex">
          <div
            className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-white/10 blur-2xl"
            aria-hidden
          />
          <div className="pointer-events-none absolute -bottom-20 -left-16 size-64 rounded-full bg-[#f5b84a]/15 blur-2xl" aria-hidden />
          <div className="relative flex items-center gap-3">
            <BrandMark className="size-11 ring-2 ring-white/20 [border-radius:0.8rem]" />
            <span className="text-xl font-bold">
              অধিকার<span className="text-[#9ff0cf]">AI</span>
            </span>
          </div>
          <div className="relative space-y-5">
            <h2 className="text-2xl leading-snug font-bold">জ্ঞানভান্ডার পরিচালনা</h2>
            <ul className="space-y-3">
              {POINTS.map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-center gap-3 text-white/90">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/15">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>
          <p className="relative text-sm text-white/70">শুধু অনুমোদিত অ্যাডমিনদের জন্য</p>
        </div>

        {/* form */}
        <form
          className="space-y-5 p-6 sm:p-10"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <div className="space-y-2">
            <BrandMark className="size-11 [border-radius:0.8rem] md:hidden" />
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-2.5 py-0.5 text-sm font-medium text-primary">
              <LockKeyhole className="size-3.5" aria-hidden /> অ্যাডমিন পোর্টাল
            </span>
            <h1 className="text-2xl font-bold">স্বাগতম</h1>
            <p className="text-muted-foreground">চালিয়ে যেতে আপনার অ্যাডমিন অ্যাকাউন্টে প্রবেশ করুন।</p>
          </div>

          <label className="block space-y-1.5">
            <span className="text-sm font-semibold">ইমেইল</span>
            <span className="relative block">
              <Mail className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@example.com"
                className={input}
              />
            </span>
          </label>

          <label className="block space-y-1.5">
            <span className="text-sm font-semibold">পাসওয়ার্ড</span>
            <span className="relative block">
              <LockKeyhole className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                type={show ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className={cn(input, "pr-11")}
              />
              <button
                type="button"
                onClick={() => setShow((v) => !v)}
                aria-label={show ? "পাসওয়ার্ড লুকান" : "পাসওয়ার্ড দেখুন"}
                className="absolute top-1/2 right-2 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
              </button>
            </span>
          </label>

          {error && (
            <p
              className="flex animate-fade-up items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
              role="alert"
              data-testid="login-error"
            >
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={!email.trim() || !password || busy}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 font-semibold text-primary-foreground shadow-card transition-all hover:bg-primary/90 active:scale-[0.98] disabled:opacity-60"
          >
            {busy && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
            {busy ? "যাচাই হচ্ছে…" : "প্রবেশ করুন"}
          </button>
          <p className="text-center text-xs text-muted-foreground">
            অ্যাকাউন্ট সার্ভারে <code className="rounded bg-secondary px-1">scripts/create_admin.py</code> দিয়ে তৈরি করা হয়।
          </p>
        </form>
      </div>
    </main>
  );
}
