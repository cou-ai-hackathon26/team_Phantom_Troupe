import { Fragment } from "react";
import type { Citation } from "@/lib/types";

const BN = "০১২৩৪৫৬৭৮৯";
const MARKER = /(\[[০-৯0-9]+\])/g;
const IS_MARKER = /^\[[০-৯0-9]+\]$/;
const STEP = /^\s*([০-৯0-9]{1,2})[.।)]\s+/;
const SUB_STEP = /^\s*([ক-ঞ])[).।]\s+/;

function markerNumber(token: string): number {
  return Number(
    token
      .slice(1, -1)
      .split("")
      .map((ch) => (BN.includes(ch) ? BN.indexOf(ch) : ch))
      .join(""),
  );
}

interface AnswerTextProps {
  text: string;
  citations: Citation[];
  onCite: (citation: Citation) => void;
}

function Inline({ text, citations, onCite }: AnswerTextProps) {
  const parts = text.split(MARKER);
  return (
    <>
      {parts.map((part, i) => {
        if (!IS_MARKER.test(part)) return <Fragment key={i}>{part}</Fragment>;
        const citation = citations.find((c) => c.marker === markerNumber(part));
        if (!citation) return null;
        return (
          <button
            key={i}
            type="button"
            onClick={() => onCite(citation)}
            className={
              citation.kind === "user"
                ? "mx-0.5 inline-flex -translate-y-1 items-center rounded-md bg-status-clarify-bg px-1.5 text-[0.8rem] font-semibold leading-5 text-status-clarify hover:opacity-80"
                : "mx-0.5 inline-flex -translate-y-1 items-center rounded-md bg-primary-soft px-1.5 text-[0.8rem] font-semibold leading-5 text-primary hover:bg-primary hover:text-primary-foreground"
            }
            aria-label={`সূত্র ${part.slice(1, -1)}: ${citation.citation}`}
          >
            {part}
          </button>
        );
      })}
    </>
  );
}

/** Renders the answer: numbered steps as a list, sub-steps (ক) indented, markers as citation buttons. */
export function AnswerText({ text, citations, onCite }: AnswerTextProps) {
  const lines = text.split("\n").filter((l) => l.trim());
  return (
    <div className="space-y-2 text-[1.05rem] leading-[1.8]">
      {lines.map((line, i) => {
        const step = line.match(STEP);
        const sub = !step && line.match(SUB_STEP);
        if (step) {
          return (
            <div key={i} className="flex gap-3">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary">
                {step[1]}
              </span>
              <p className="min-w-0">
                <Inline text={line.slice(step[0].length)} citations={citations} onCite={onCite} />
              </p>
            </div>
          );
        }
        if (sub) {
          return (
            <p key={i} className="ml-3 border-l-2 border-primary-soft pl-3 sm:ml-10">
              <span className="font-semibold text-muted-foreground">{sub[1]}) </span>
              <Inline text={line.slice(sub[0].length)} citations={citations} onCite={onCite} />
            </p>
          );
        }
        return (
          <p key={i}>
            <Inline text={line} citations={citations} onCite={onCite} />
          </p>
        );
      })}
    </div>
  );
}
