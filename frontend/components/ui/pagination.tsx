"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { toBnDigits } from "@/lib/bn";
import { cn } from "@/lib/utils";

/** Page numbers to show: first, last, current ±1, with gaps ("…") between. */
function pageList(page: number, pages: number): (number | "gap")[] {
  const wanted = new Set([1, pages, page - 1, page, page + 1].filter((p) => p >= 1 && p <= pages));
  const sorted = [...wanted].sort((a, b) => a - b);
  const out: (number | "gap")[] = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push("gap");
    out.push(p);
  });
  return out;
}

interface PaginationProps {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  disabled?: boolean;
  unit?: string; // "নথি", "অংশ"
  className?: string;
}

export function Pagination({ page, pages, total, pageSize, onPage, disabled, unit = "টি", className }: PaginationProps) {
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const btn =
    "flex h-9 min-w-9 items-center justify-center rounded-full px-2 text-sm transition-colors disabled:pointer-events-none disabled:opacity-40";

  return (
    <nav aria-label="পৃষ্ঠা" className={cn("flex flex-col items-center gap-2 sm:flex-row sm:justify-between", className)}>
      <p className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
        {toBnDigits(from)}–{toBnDigits(to)} · মোট {toBnDigits(total)}{unit}
      </p>
      {pages > 1 && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onPage(page - 1)}
            disabled={disabled || page <= 1}
            aria-label="আগের পৃষ্ঠা"
            className={cn(btn, "border bg-card hover:border-primary/40 hover:text-primary")}
          >
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          {/* phones: compact "২ / ১০"; wider screens: numbered pages */}
          <span className="px-2 text-sm tabular-nums sm:hidden">
            {toBnDigits(page)} / {toBnDigits(pages)}
          </span>
          <span className="hidden items-center gap-1 sm:flex">
            {pageList(page, pages).map((p, i) =>
              p === "gap" ? (
                <span key={`gap-${i}`} className="px-1 text-muted-foreground" aria-hidden>
                  …
                </span>
              ) : (
                <button
                  key={p}
                  type="button"
                  onClick={() => onPage(p)}
                  disabled={disabled}
                  aria-current={p === page ? "page" : undefined}
                  aria-label={`পৃষ্ঠা ${toBnDigits(p)}`}
                  className={cn(
                    btn,
                    "tabular-nums",
                    p === page ? "bg-primary font-semibold text-primary-foreground shadow-card" : "hover:bg-secondary",
                  )}
                >
                  {toBnDigits(p)}
                </button>
              ),
            )}
          </span>
          <button
            type="button"
            onClick={() => onPage(page + 1)}
            disabled={disabled || page >= pages}
            aria-label="পরের পৃষ্ঠা"
            className={cn(btn, "border bg-card hover:border-primary/40 hover:text-primary")}
          >
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
      )}
    </nav>
  );
}
