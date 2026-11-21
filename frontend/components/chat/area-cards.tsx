import { AREAS } from "@/lib/areas";

interface AreaCardsProps {
  onAsk: (question: string) => void;
  disabled?: boolean;
}

export function AreaCards({ onAsk, disabled }: AreaCardsProps) {
  return (
    <section aria-labelledby="areas-heading" className="space-y-5">
      <div className="space-y-1">
        <h1 id="areas-heading" className="text-2xl font-semibold sm:text-[1.75rem]">
          আপনার প্রশ্ন বলুন বা লিখুন
        </h1>
        <p className="text-muted-foreground">
          উত্তর আসবে সরকারি আইন ও নথি থেকে, সূত্রসহ। নিচের কোনো প্রশ্নে চাপ দিয়েও শুরু করতে পারেন।
        </p>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2">
        {AREAS.map((area) => {
          const Icon = area.icon;
          return (
            <li key={area.id} className="rounded-xl border bg-card p-4">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
                  <Icon className="size-5" aria-hidden />
                </span>
                <div className="min-w-0">
                  <h2 className="font-semibold leading-snug">{area.label}</h2>
                  <p className="text-sm text-muted-foreground">{area.description}</p>
                </div>
              </div>
              <div className="mt-3 flex flex-col gap-2">
                {area.examples.map((q) => (
                  <button
                    key={q}
                    type="button"
                    disabled={disabled}
                    onClick={() => onAsk(q)}
                    className="rounded-lg border border-transparent bg-secondary px-3 py-2 text-left text-[0.95rem] leading-snug transition-colors hover:border-primary/30 hover:bg-primary-soft disabled:opacity-60"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
