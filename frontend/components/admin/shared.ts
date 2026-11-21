import { ApiError } from "@/lib/api";

export type AdminInfo = { email: string; llm_model: string | null; embedding_model: string };

export const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "কিছু একটা সমস্যা হয়েছে।");

export const fieldClass =
  "w-full rounded-xl border bg-background px-3.5 py-2.5 outline-none transition-shadow placeholder:text-muted-foreground focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/10";
