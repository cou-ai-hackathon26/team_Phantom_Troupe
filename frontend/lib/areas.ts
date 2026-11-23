import { Briefcase, HandCoins, Landmark, Scale, ShieldCheck, type LucideIcon } from "lucide-react";
import type { Area } from "./types";

export interface AreaInfo {
  id: Area;
  label: string;
  description: string;
  icon: LucideIcon;
  examples: string[];
}

// Example chips are questions only (no facts). Keep them answerable from ingested documents.
export const AREAS: AreaInfo[] = [
  {
    id: "land",
    label: "জমি ও নামজারি",
    description: "নামজারি, খতিয়ান, ভূমি উন্নয়ন কর",
    icon: Landmark,
    examples: ["নামজারি বা মিউটেশন কী?", "ভূমি উন্নয়ন কর কীভাবে দিতে হয়?"],
  },
  {
    id: "gd",
    label: "জিডি",
    description: "থানায় সাধারণ ডায়েরি, হারানো জিনিস",
    icon: ShieldCheck,
    examples: ["থানায় জিডি করতে কী কী লাগে?", "জাতীয় পরিচয়পত্র হারালে কী করব?"],
  },
  {
    id: "allowance",
    label: "সামাজিক ভাতা",
    description: "বয়স্ক, বিধবা ও প্রতিবন্ধী ভাতা",
    icon: HandCoins,
    examples: ["বয়স্ক ভাতা পাওয়ার যোগ্যতা কী?", "বিধবা ভাতার জন্য কোথায় আবেদন করব?"],
  },
  {
    id: "labour",
    label: "শ্রমিক অধিকার",
    description: "নিয়োগ, ছুটি, লে-অফ, ছাঁটাই",
    icon: Briefcase,
    examples: ["লে-অফ হলে শ্রমিক কি ক্ষতিপূরণ পায়?", "চাকরি থেকে ছাঁটাই করলে কী কী পাওনা পাব?"],
  },
  {
    id: "general",
    label: "অন্যান্য আইন",
    description: "সংবিধান, বাংলাদেশের অন্যান্য আইন, মানবাধিকার কমিশন",
    icon: Scale,
    examples: [
      "সংবিধানের অনুচ্ছেদ ২৭ কী বলে?",
      "তথ্য অধিকার আইনে কীভাবে তথ্য চাইতে হয়?",
      "জাতীয় মানবাধিকার কমিশনে কীভাবে অভিযোগ করা যায়?",
    ],
  },
];

export const AREA_LABEL: Record<string, string> = Object.fromEntries(AREAS.map((a) => [a.id, a.label]));

export function areaLabel(area: string): string {
  return AREA_LABEL[area] ?? "নির্ধারিত হয়নি";
}
