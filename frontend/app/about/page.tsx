import type { Metadata } from "next";
import { FileSearch, MessageCircleQuestion, ShieldCheck, Sparkles } from "lucide-react";
import { EvalSection } from "@/components/eval-section";

export const metadata: Metadata = { title: "কীভাবে কাজ করে — অধিকারAI" };

const STEPS = [
  { icon: MessageCircleQuestion, title: "প্রশ্ন", text: "আপনি নিজের ভাষায় বলেন বা লেখেন: প্রমিত বাংলা, আঞ্চলিক ভাষা, বাংলিশ বা ইংরেজি।" },
  { icon: FileSearch, title: "নথি খোঁজা", text: "প্রশ্নটি প্রমিত বাংলায় সাজিয়ে অর্থ ও শব্দ, দুইভাবে সরকারি নথিতে খোঁজা হয়।" },
  { icon: ShieldCheck, title: "যাচাই", text: "উত্তরের প্রতিটি সূত্র ও সংখ্যা মূল নথির সাথে মিলিয়ে দেখা হয়। না মিললে সতর্ক করা হয়।" },
  { icon: Sparkles, title: "উত্তর", text: "সহজ বাংলায় ধাপে ধাপে উত্তর, সাথে সূত্র। নথিতে না থাকলে সরাসরি জানিয়ে দেওয়া হয়।" },
];

const CREDITS = [
  ["মডেল ও সেবা", "intfloat/multilingual-e5-base (লোকাল এমবেডিং) · Groq (LLM ও Whisper) · Supabase PostgreSQL · Qdrant Cloud · ব্রাউজারের Web Speech API"],
  ["ব্যাকএন্ড", "FastAPI · Pydantic · SQLAlchemy · asyncpg · qdrant-client · sentence-transformers · PyTorch · rank-bm25 · PyMuPDF"],
  ["ফ্রন্টএন্ড", "Next.js · React · TypeScript · Tailwind CSS · shadcn/ui · Radix UI · lucide-react · Hind Siliguri ফন্ট"],
  ["এআই কোডিং সহকারী", "Claude Code (Anthropic)"],
];

export default function AboutPage() {
  return (
    <main className="mx-auto max-w-3xl space-y-10 px-4 py-8">
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold">অধিকারAI কীভাবে কাজ করে</h1>
        <p className="text-muted-foreground">
          অধিকারAI শুধু সরকারি আইন ও নথি থেকে উত্তর দেয় এবং প্রতিটি উত্তরের সাথে সূত্র দেখায়। নথিতে উত্তর না থাকলে অনুমান
          না করে জাতীয় হেল্পলাইন ৩৩৩-এর কথা বলে।
        </p>
      </section>

      <section aria-labelledby="steps-heading" className="space-y-4">
        <h2 id="steps-heading" className="text-xl font-semibold">চার ধাপে উত্তর</h2>
        <ol className="grid gap-3 sm:grid-cols-4">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.title} className="relative rounded-xl border bg-card p-4">
                <span className="flex size-10 items-center justify-center rounded-lg bg-primary-soft text-primary">
                  <Icon className="size-5" aria-hidden />
                </span>
                <h3 className="mt-3 font-semibold">
                  {["১", "২", "৩", "৪"][i]}. {step.title}
                </h3>
                <p className="mt-1 text-[0.95rem] text-muted-foreground">{step.text}</p>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="data-heading" className="space-y-3">
        <h2 id="data-heading" className="text-xl font-semibold">তথ্যের উৎস</h2>
        <ul className="space-y-2">
          <li className="rounded-xl border bg-card p-4">
            <p className="font-semibold">বাংলাদেশ শ্রম আইন, ২০০৬</p>
            <p className="text-[0.95rem] text-muted-foreground">
              আইন ও বিচার বিভাগের ওয়েবসাইট (
              <a href="https://bdlaws.minlaw.gov.bd/act-952.html" target="_blank" rel="noopener noreferrer" className="text-primary underline-offset-4 hover:underline">
                bdlaws.minlaw.gov.bd
              </a>
              ) থেকে নেওয়া প্রস্তাবনা এবং ধারা ১ থেকে ২০, সংশোধনী টীকাসহ।
            </p>
          </li>
          <li className="rounded-xl border border-dashed p-4 text-[0.95rem] text-muted-foreground">
            জমি, জিডি ও সামাজিক ভাতার নথি যুক্ত হচ্ছে। যে বিষয়ের নথি নেই, সে বিষয়ে অধিকারAI উত্তর না দিয়ে জানিয়ে দেয়।
          </li>
        </ul>
      </section>

      <EvalSection />

      <section aria-labelledby="limits-heading" className="space-y-3">
        <h2 id="limits-heading" className="text-xl font-semibold">সীমাবদ্ধতা</h2>
        <ul className="list-disc space-y-1.5 pl-5 text-[0.98rem]">
          <li>এটি আইনি পরামর্শ নয়। গুরুত্বপূর্ণ সিদ্ধান্তের আগে সংশ্লিষ্ট অফিস বা আইনজীবীর সাথে কথা বলুন।</li>
          <li>উত্তর শুধু যুক্ত করা নথি থেকে আসে; নথির বাইরের নিয়ম বা সাম্প্রতিক পরিবর্তন এতে নাও থাকতে পারে।</li>
          <li>পুরনো সরকারি নথিতে লেখার কিছু ত্রুটি থাকতে পারে। সন্দেহ হলে মূল উৎস খুলে দেখুন।</li>
          <li>আপনার প্রশ্ন বা কথোপকথন সংরক্ষণ করা হয় না; ব্যক্তিগত তথ্য (এনআইডি, ফোন নম্বর) দেবেন না।</li>
        </ul>
      </section>

      <section aria-labelledby="credits-heading" className="space-y-3">
        <h2 id="credits-heading" className="text-xl font-semibold">কৃতজ্ঞতা</h2>
        <dl className="space-y-2">
          {CREDITS.map(([k, v]) => (
            <div key={k} className="rounded-xl border bg-card p-4">
              <dt className="font-semibold">{k}</dt>
              <dd className="text-[0.95rem] text-muted-foreground">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="text-muted-foreground">
          তৈরি করেছে <span className="font-semibold text-foreground">টিম Phantom Troupe</span>, CoU AI Hackathon ২০২৬।
        </p>
      </section>
    </main>
  );
}
