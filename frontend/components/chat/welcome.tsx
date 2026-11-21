import type { ReactNode } from "react";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { AREAS } from "@/lib/areas";

// one starter question from four areas (questions only, no facts)
const SUGGESTIONS = (["land", "allowance", "labour", "general"] as const).map((id) => {
  const area = AREAS.find((a) => a.id === id)!;
  return { icon: area.icon, question: area.examples[0] };
});

interface WelcomeProps {
  onAsk: (question: string) => void;
  disabled?: boolean;
  composer: ReactNode;
}

/** Empty state: one focused question box with a few starters. */
export function Welcome({ onAsk, disabled, composer }: WelcomeProps) {
  return (
    <section aria-labelledby="welcome-heading" className="mx-auto flex w-full max-w-2xl flex-col items-center text-center">
      <BrandMark className="size-14 animate-fade-up shadow-card [border-radius:1rem] sm:size-16" />
      <h1
        id="welcome-heading"
        className="mt-5 animate-fade-up text-[1.85rem] leading-tight font-bold tracking-tight [animation-delay:60ms] sm:text-[2.6rem]"
      >
        আপনার অধিকার, <span className="text-primary">সহজ বাংলায়</span>
      </h1>
      <p className="mt-2 max-w-md animate-fade-up text-muted-foreground [animation-delay:120ms] sm:text-lg">
        সরকারি আইন ও নথি থেকে সূত্রসহ উত্তর। লিখে বা কথা বলে প্রশ্ন করুন।
      </p>

      <div className="mt-7 w-full animate-fade-up text-left [animation-delay:180ms]">{composer}</div>

      <ul className="mt-5 grid w-full animate-fade-up gap-2 [animation-delay:260ms] sm:grid-cols-2">
        {SUGGESTIONS.map(({ icon: Icon, question }) => (
          <li key={question}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onAsk(question)}
              className="group flex h-full w-full items-center gap-3 rounded-2xl border bg-card/80 px-4 py-3 text-left text-[0.95rem] leading-snug transition-all hover:border-primary/30 hover:bg-card hover:shadow-card disabled:pointer-events-none disabled:opacity-60"
            >
              <Icon className="size-4 shrink-0 text-primary" aria-hidden />
              <span className="flex-1">{question}</span>
              <ArrowUpRight
                className="size-4 shrink-0 text-muted-foreground opacity-0 transition-all group-hover:opacity-100 group-focus-visible:opacity-100"
                aria-hidden
              />
            </button>
          </li>
        ))}
      </ul>

      <p className="mt-6 inline-flex animate-fade-up items-center gap-1.5 text-sm text-muted-foreground [animation-delay:320ms]">
        <ShieldCheck className="size-4 text-primary" aria-hidden />
        শুধু সরকারি নথি থেকে উত্তর, প্রতিটি তথ্যের সূত্রসহ
      </p>
    </section>
  );
}
