import { Ban, CircleCheck, CircleHelp, TriangleAlert } from "lucide-react";
import type { Status } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS: Record<Status, { label: string; className: string; Icon: typeof CircleCheck }> = {
  answered: { label: "উত্তর পাওয়া গেছে", className: "bg-status-answered-bg text-status-answered", Icon: CircleCheck },
  partial: { label: "আংশিক যাচাই", className: "bg-status-partial-bg text-status-partial", Icon: TriangleAlert },
  refused: { label: "উত্তর পাওয়া যায়নি", className: "bg-status-refused-bg text-status-refused", Icon: Ban },
  clarify: { label: "আরও তথ্য দরকার", className: "bg-status-clarify-bg text-status-clarify", Icon: CircleHelp },
};

export function StatusBadge({ status }: { status: Status }) {
  const { label, className, Icon } = STATUS[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-semibold", className)}>
      <Icon className="size-4" aria-hidden />
      {label}
    </span>
  );
}
