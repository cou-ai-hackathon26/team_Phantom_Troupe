import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BadgeCheck, FileText, HeartHandshake, MessageCircle, Mic, PhoneCall, Quote, ShieldCheck } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { AREAS } from "@/lib/areas";

export const metadata: Metadata = { title: "কীভাবে কাজ করে — অধিকারAI" };

const STEPS = [
  {
    icon: Mic,
    title: "প্রশ্ন করুন",
    text: "যে ভাষায় স্বচ্ছন্দ, সেভাবেই লিখুন বা মাইকে বলুন। প্রমিত বাংলা, আঞ্চলিক ভাষা, বাংলিশ বা ইংরেজি, সবই চলবে।",
  },
  {
    icon: MessageCircle,
    title: "সহজ উত্তর পান",
    text: "অধিকারAI সরকারি আইন ও নথি পড়ে আপনার প্রশ্নের উত্তর সহজ বাংলায়, দরকার হলে ধাপে ধাপে সাজিয়ে দেয়।",
  },
  {
    icon: FileText,
    title: "সূত্র দেখে নিশ্চিত হন",
    text: "উত্তরের প্রতিটি তথ্যের পাশে সূত্র থাকে। চাপ দিলেই আইনের মূল লেখাটি দেখতে পাবেন।",
  },
];

const PROMISES = [
  { icon: ShieldCheck, title: "শুধু সরকারি নথি", text: "উত্তর আসে আইন, বিধিমালা ও সরকারি নির্দেশিকা থেকে; অনুমান থেকে নয়।" },
  { icon: Quote, title: "প্রতিটি উত্তরে সূত্র", text: "কোন আইনের কোন ধারা থেকে তথ্যটি এসেছে, তা সবসময় দেখানো হয়।" },
  { icon: PhoneCall, title: "না জানলে সরাসরি বলে", text: "নথিতে উত্তর না পেলে ভুল তথ্য না দিয়ে জাতীয় হেল্পলাইন ৩৩৩-এর পরামর্শ দেয়।" },
  { icon: BadgeCheck, title: "ওয়েবের তথ্য আলাদা করে চেনানো", text: "কখনো সরকারি ওয়েবসাইট থেকে তথ্য নিলে তা আলাদা চিহ্নে দেখায়, লিংকসহ।" },
];

export default function AboutPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:py-16">
      {/* intro */}
      <section className="animate-fade-up text-center">
        <BrandMark className="mx-auto size-14 [border-radius:1rem]" />
        <h1 className="mt-5 text-[1.85rem] leading-tight font-bold tracking-tight sm:text-4xl">
          আইনের ভাষা, <span className="text-primary">আপনার ভাষায়</span>
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-muted-foreground sm:text-lg">
          জমি, থানা, সরকারি ভাতা বা কর্মক্ষেত্রের অধিকার নিয়ে প্রশ্ন থাকলে আর আইনের মোটা বই ঘাঁটতে হবে না। প্রশ্ন করুন,
          অধিকারAI সরকারি নথি থেকে উত্তর খুঁজে দেবে।
        </p>
      </section>

      {/* steps */}
      <section aria-labelledby="steps-heading" className="mt-14 sm:mt-20">
        <h2 id="steps-heading" className="text-center text-2xl font-bold">
          তিনটি সহজ ধাপ
        </h2>
        <ol className="relative mt-8 grid gap-4 sm:grid-cols-3 sm:gap-6">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li
              key={title}
              className="relative animate-fade-up rounded-3xl border bg-card p-6 shadow-card"
              style={{ animationDelay: `${100 + i * 90}ms` }}
            >
              <div className="flex items-center justify-between">
                <span className="flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                  <Icon className="size-6" aria-hidden />
                </span>
                <span className="text-4xl font-bold text-primary/15" aria-hidden>
                  {["১", "২", "৩"][i]}
                </span>
              </div>
              <h3 className="mt-4 text-lg font-semibold">{title}</h3>
              <p className="mt-1 text-[0.97rem] text-muted-foreground">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* topics */}
      <section aria-labelledby="topics-heading" className="mt-14 sm:mt-20">
        <h2 id="topics-heading" className="text-center text-2xl font-bold">
          যে বিষয়ে জানতে পারবেন
        </h2>
        <ul className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {AREAS.map(({ id, icon: Icon, label, description }) => (
            <li key={id} className="flex items-start gap-3 rounded-2xl border bg-card p-4">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
                <Icon className="size-5" aria-hidden />
              </span>
              <div>
                <h3 className="font-semibold">{label}</h3>
                <p className="text-sm text-muted-foreground">{description}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* trust */}
      <section aria-labelledby="trust-heading" className="mt-14 rounded-3xl border bg-card p-6 shadow-card sm:mt-20 sm:p-10">
        <div className="flex items-center gap-2 text-primary">
          <HeartHandshake className="size-6" aria-hidden />
          <h2 id="trust-heading" className="text-2xl font-bold text-foreground">
            কেন ভরসা করবেন
          </h2>
        </div>
        <ul className="mt-6 grid gap-6 sm:grid-cols-2">
          {PROMISES.map(({ icon: Icon, title, text }) => (
            <li key={title} className="flex gap-3">
              <Icon className="mt-1 size-5 shrink-0 text-primary" aria-hidden />
              <div>
                <h3 className="font-semibold">{title}</h3>
                <p className="text-[0.97rem] text-muted-foreground">{text}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* keep in mind */}
      <section aria-labelledby="note-heading" className="mt-10 rounded-2xl bg-status-partial-bg p-5 text-status-partial">
        <h2 id="note-heading" className="font-semibold">
          মনে রাখবেন
        </h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[0.97rem]">
          <li>এটি আইনি পরামর্শ নয়। গুরুত্বপূর্ণ সিদ্ধান্তের আগে সংশ্লিষ্ট অফিস বা আইনজীবীর সাথে কথা বলুন।</li>
          <li>আইন ও নিয়ম বদলাতে পারে; সন্দেহ হলে সূত্রে দেওয়া মূল লেখা দেখে নিন।</li>
          <li>প্রশ্নে এনআইডি নম্বর, ফোন নম্বর বা অন্য ব্যক্তিগত তথ্য দেবেন না।</li>
        </ul>
      </section>

      {/* call to action */}
      <section className="mt-14 text-center sm:mt-20">
        <h2 className="text-2xl font-bold">আপনার প্রশ্নটি কী?</h2>
        <Link
          href="/"
          className="mt-5 inline-flex items-center gap-2 rounded-full bg-primary px-7 py-3.5 text-lg font-semibold text-primary-foreground shadow-card transition-all hover:gap-3 hover:bg-primary/90 active:scale-95"
        >
          প্রশ্ন করুন <ArrowRight className="size-5" aria-hidden />
        </Link>
        <p className="mt-10 text-sm text-muted-foreground">
          তৈরি করেছে টিম Phantom Troupe · CoU AI Hackathon ২০২৬
        </p>
      </section>
    </main>
  );
}
