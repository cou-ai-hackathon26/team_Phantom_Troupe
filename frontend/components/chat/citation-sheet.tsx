"use client";

import { ExternalLink, FileText } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useMediaQuery } from "@/hooks/use-media-query";
import { toBnDigits } from "@/lib/bn";

export interface SourceView {
  marker?: number;
  citation: string;
  title: string;
  text: string;
  notes: string[];
  sourceUrl: string | null;
  loading?: boolean;
}

interface CitationSheetProps {
  source: SourceView | null;
  onOpenChange: (open: boolean) => void;
}

/** Full source excerpt: side sheet on desktop, bottom sheet on mobile. */
export function CitationSheet({ source, onOpenChange }: CitationSheetProps) {
  const desktop = useMediaQuery("(min-width: 768px)");
  return (
    <Sheet open={source !== null} onOpenChange={onOpenChange}>
      <SheetContent
        side={desktop ? "right" : "bottom"}
        className={desktop ? "w-full gap-0 sm:max-w-lg" : "max-h-[85dvh] gap-0 rounded-t-2xl"}
      >
        {source && (
          <>
            <SheetHeader className="border-b pr-12">
              <p className="flex items-center gap-2 text-sm font-semibold text-primary">
                <FileText className="size-4" aria-hidden />
                {source.marker ? `সূত্র ${toBnDigits(source.marker)}` : "সূত্র"}
              </p>
              <SheetTitle className="text-lg leading-snug">{source.citation}</SheetTitle>
              <SheetDescription className="text-base text-foreground/80">{source.title}</SheetDescription>
            </SheetHeader>
            <div className="flex-1 overflow-y-auto px-4 py-4">
              {source.loading ? (
                <p className="text-muted-foreground">লোড হচ্ছে…</p>
              ) : (
                <div className="whitespace-pre-line rounded-lg bg-secondary/60 p-4 text-[0.98rem] leading-[1.85]">
                  {source.text}
                </div>
              )}
              {source.notes.length > 0 && (
                <details className="mt-4 rounded-lg border p-3">
                  <summary className="cursor-pointer font-semibold">
                    সংশোধনী টীকা ({toBnDigits(source.notes.length)})
                  </summary>
                  <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                    {source.notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ol>
                </details>
              )}
              <p className="mt-4 text-sm text-muted-foreground">
                এখানে নথির প্রাসঙ্গিক অংশ দেখানো হয়েছে। চূড়ান্ত নিশ্চয়তার জন্য মূল উৎস দেখুন।
              </p>
            </div>
            {source.sourceUrl && (
              <div className="border-t p-4">
                <a
                  href={source.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  মূল উৎস দেখুন <ExternalLink className="size-4" aria-hidden />
                </a>
              </div>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
