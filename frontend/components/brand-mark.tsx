import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * AdhikarAI mark: a speech bubble (your question) holding a check (a verified answer),
 * with a small spark for the assistant. Same drawing as app/icon.svg.
 */
export function BrandMark({ className, title }: { className?: string; title?: string }) {
  const id = useId();
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("size-9 shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <defs>
        <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#0f8a63" />
          <stop offset="1" stopColor="#095c42" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${id}-bg)`} />
      <path
        d="M11.5 7.5h9a4.5 4.5 0 0 1 4.5 4.5v5a4.5 4.5 0 0 1-4.5 4.5h-5l-4.2 3.6c-.4.3-.9 0-.9-.4v-3.4A4.5 4.5 0 0 1 7 17v-5a4.5 4.5 0 0 1 4.5-4.5Z"
        fill="#fff"
      />
      <path
        d="m11.6 14.4 2.6 2.6 5.4-5.3"
        fill="none"
        stroke="#0b6e4f"
        strokeWidth="2.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M26 3.6c.3 1.5.9 2.1 2.4 2.4-1.5.3-2.1.9-2.4 2.4-.3-1.5-.9-2.1-2.4-2.4 1.5-.3 2.1-.9 2.4-2.4Z" fill="#f5b84a" />
    </svg>
  );
}
