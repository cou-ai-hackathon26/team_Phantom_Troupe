"use client";

import { useState } from "react";
import { ArrowUpRight, FileCheck2, Languages, Mic, PhoneCall, Search, ShieldCheck, Sparkles } from "lucide-react";
import { AREAS } from "@/lib/areas";
import type { Area } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AreaCardsProps {
  onAsk: (question: string) => void;
  disabled?: boolean;
}

const FEATURES = [
  { icon: Mic, label: "কথা বলে প্রশ্ন" },
  { icon: FileCheck2, label: "প্রতিটি উত্তরে সূত্র" },
  { icon: Languages, label: "বাংলা, আঞ্চলিক, Banglish, English" },
  { icon: PhoneCall, label: "না জানলে ৩৩৩-এর পরামর্শ" },
];

const STEPS = [
  { icon: Sparkles, title: "প্রশ্ন করুন", text: "নিজের ভাষায় লিখুন বা মাইকে বলুন।" },
  { icon: Search, title: "নথি খোঁজা", text: "সরকারি আইন ও নথি থেকে প্রাসঙ্গিক অংশ খোঁজা হয়।" },
  { icon: ShieldCheck, title: "যাচাই করা উত্তর", text: "প্রতিটি তথ্য সূত্রের সাথে মিলিয়ে দেখানো হয়।" },
];

/** Home screen: hero, topic switcher with example questions, and how it works. */
export function AreaCards({ onAsk, disabled }: AreaCardsProps) {
  const [selected, setSelected] = useState<Area>(AREAS[0].id);
  const area = AREAS.find((a) => a.id === selected) ?? AREAS[0];
  const AreaIcon = area.icon;

  return (
    <div className="space-y-10 pb-4 sm:space-y-12">
      {/* hero */}
      <section aria-labelledby="hero-heading" className="animate-fade-up space-y-5 pt-2 text-center sm:pt-6">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary-soft px-3 py-1 text-sm font-medium text-primary">
          <ShieldCheck className="size-4" aria-hidden />
          শুধু সরকারি নথি থেকে, সূত্রসহ উত্তর
        </span>
        <h1 id="hero-heading" className="text-[1.9rem] leading-tight font-bold tracking-tight sm:text-5xl sm:leading-[1.15]">
          আপনার অধিকার,{" "}
          <span className="bg-gradient-to-r from-primary via-[#14a06f] to-[#c98a0b] bg-clip-text text-transparent">
            সহজ বাংলায়
          </span>
        </h1>
        <p className="mx-auto max-w-xl text-[1.02rem] text-muted-foreground sm:text-lg">
          জমি, জিডি, সামাজিক ভাতা, শ্রমিক অধিকার বা সংবিধান নিয়ে প্রশ্ন বলুন বা লিখুন। উত্তর আসবে আইন ও সরকারি নথি
          থেকে, প্রতিটি তথ্যের সূত্রসহ।
        </p>
        <ul className="mx-auto flex max-w-2xl flex-wrap justify-center gap-2">
          {FEATURES.map(({ icon: Icon, label }, i) => (
            <li
              key={label}
              className="animate-fade-up inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1.5 text-sm shadow-card"
              style={{ animationDelay: `${120 + i * 70}ms` }}
            >
              <Icon className="size-4 text-primary" aria-hidden />
              {label}
            </li>
          ))}
        </ul>
      </section>

      {/* topic switcher */}
      <section aria-labelledby="topics-heading" className="animate-fade-up space-y-4 [animation-delay:200ms]">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 id="topics-heading" className="text-xl font-semibold">
              কোন বিষয়ে জানতে চান?
            </h2>
            <p className="text-sm text-muted-foreground">বিষয় বেছে নিন, তারপর নিচের কোনো প্রশ্নে চাপ দিন।</p>
          </div>
        </div>

        <div
          role="tablist"
          aria-label="বিষয়"
          className="no-scrollbar -mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0"
        >
          {AREAS.map((a) => {
            const Icon = a.icon;
            const active = a.id === selected;
            return (
              <button
                key={a.id}
                type="button"
                role="tab"
                id={`tab-${a.id}`}
                aria-selected={active}
                aria-controls="topic-panel"
                onClick={() => setSelected(a.id)}
                className={cn(
                  "flex shrink-0 snap-start items-center gap-2 rounded-full border px-4 py-2 text-[0.95rem] font-medium transition-all",
                  active
                    ? "border-primary bg-primary text-primary-foreground shadow-card"
                    : "bg-card text-foreground hover:border-primary/40 hover:bg-primary-soft",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {a.label}
              </button>
            );
          })}
        </div>

        <div
          id="topic-panel"
          role="tabpanel"
          aria-labelledby={`tab-${area.id}`}
          key={area.id}
          className="animate-fade-up overflow-hidden rounded-2xl border bg-card shadow-card"
        >
          <div className="flex items-center gap-3 border-b bg-gradient-to-r from-primary-soft to-transparent p-4 sm:p-5">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-card">
              <AreaIcon className="size-6" aria-hidden />
            </span>
            <div className="min-w-0">
              <h3 className="text-lg font-semibold leading-snug">{area.label}</h3>
              <p className="text-sm text-muted-foreground">{area.description}</p>
            </div>
          </div>
          <ul className="grid gap-2 p-3 sm:grid-cols-2 sm:p-4">
            {area.examples.map((q, i) => (
              <li key={q} className="animate-fade-up" style={{ animationDelay: `${80 + i * 60}ms` }}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onAsk(q)}
                  className="group flex h-full w-full items-center justify-between gap-3 rounded-xl border border-transparent bg-secondary/70 px-4 py-3 text-left text-[0.98rem] leading-snug transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:bg-primary-soft hover:shadow-card active:translate-y-0 disabled:pointer-events-none disabled:opacity-60"
                >
                  <span>{q}</span>
                  <ArrowUpRight
                    className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-primary"
                    aria-hidden
                  />
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* how it works */}
      <section aria-labelledby="how-heading" className="animate-fade-up space-y-4 [animation-delay:300ms]">
        <h2 id="how-heading" className="text-xl font-semibold">
          কীভাবে কাজ করে
        </h2>
        <ol className="grid gap-3 sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="relative flex gap-3 rounded-2xl border bg-card p-4 sm:flex-col">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
                <Icon className="size-5" aria-hidden />
              </span>
              <div>
                <h3 className="font-semibold">
                  <span className="text-primary">{["১", "২", "৩"][i]}.</span> {title}
                </h3>
                <p className="text-[0.95rem] text-muted-foreground">{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
