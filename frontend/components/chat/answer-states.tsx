import { RefreshCw, TriangleAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

export function AnswerSkeleton() {
  return (
    <div className="space-y-4 rounded-xl border bg-card p-4 sm:p-5" aria-busy="true">
      <p className="flex items-center gap-2 text-muted-foreground">
        <span className="relative flex size-2.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60 motion-reduce:animate-none" />
          <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
        </span>
        নথি খুঁজছি…
      </p>
      <Skeleton className="h-4 w-11/12" />
      <Skeleton className="h-4 w-9/12" />
      <Skeleton className="h-4 w-10/12" />
    </div>
  );
}

export function AnswerError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-card p-4 sm:flex-row sm:items-center" role="alert">
      <div className="flex flex-1 gap-2">
        <TriangleAlert className="mt-1 size-5 shrink-0 text-destructive" aria-hidden />
        <p>{message}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2 font-semibold hover:bg-secondary"
      >
        <RefreshCw className="size-4" aria-hidden /> আবার চেষ্টা করুন
      </button>
    </div>
  );
}

export function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[1.05rem] leading-relaxed text-primary-foreground">
        {text}
      </p>
    </div>
  );
}
