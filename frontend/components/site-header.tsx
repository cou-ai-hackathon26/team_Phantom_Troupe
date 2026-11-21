"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "হোম" },
  { href: "/sources", label: "নথিসমূহ" },
  { href: "/about", label: "কীভাবে কাজ করে" },
];

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-3">
        <Link href="/" className="group flex flex-col leading-tight" aria-label="অধিকারAI — হোম">
          <span className="text-xl font-semibold tracking-tight">
            <span className="text-primary">অধিকার</span>AI
          </span>
          <span className="hidden text-sm text-muted-foreground sm:block">সরকারি নথি থেকে আপনার অধিকারের উত্তর</span>
        </Link>
        <nav aria-label="প্রধান মেনু">
          <ul className="flex items-center gap-1 text-[0.95rem]">
            {NAV.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "rounded-lg px-3 py-1.5 transition-colors hover:bg-secondary",
                      active ? "font-semibold text-primary" : "text-muted-foreground",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
