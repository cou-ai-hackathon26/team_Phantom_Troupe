"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenText, House, Info, Menu, Scale, ShieldUser } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "হোম", icon: House },
  { href: "/sources", label: "নথিসমূহ", icon: BookOpenText },
  { href: "/about", label: "কীভাবে কাজ করে", icon: Info },
  { href: "/admin", label: "অ্যাডমিন", icon: ShieldUser },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function Logo() {
  return (
    <Link href="/" className="group flex items-center gap-2.5" aria-label="অধিকারAI — হোম">
      <span className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[#0f8a63] text-primary-foreground shadow-card transition-transform group-hover:-rotate-6 sm:size-10">
        <Scale className="size-5" aria-hidden />
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-lg font-bold tracking-tight sm:text-xl">
          <span className="text-primary">অধিকার</span>AI
        </span>
        <span className="hidden text-xs text-muted-foreground sm:block">সরকারি নথি থেকে আপনার অধিকারের উত্তর</span>
      </span>
    </Link>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="glass sticky top-0 z-30 border-b">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
        <Logo />

        <nav aria-label="প্রধান মেনু" className="hidden md:block">
          <ul className="flex items-center gap-1 rounded-full border bg-card/70 p-1 text-[0.95rem]">
            {NAV.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block whitespace-nowrap rounded-full px-4 py-1.5 transition-all",
                      active
                        ? "bg-primary font-semibold text-primary-foreground shadow-card"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label="মেনু খুলুন"
            aria-expanded={open}
            className="flex size-10 items-center justify-center rounded-full border bg-card text-foreground md:hidden"
          >
            <Menu className="size-5" aria-hidden />
          </button>
        </div>
      </div>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-[82%] max-w-xs gap-0 p-0">
          <SheetHeader className="border-b p-4">
            <SheetTitle className="text-left">
              <span className="text-primary">অধিকার</span>AI
            </SheetTitle>
            <SheetDescription className="text-left">সরকারি নথি থেকে আপনার অধিকারের উত্তর</SheetDescription>
          </SheetHeader>
          <nav aria-label="মোবাইল মেনু" className="p-3">
            <ul className="space-y-1">
              {NAV.map((item, i) => {
                const active = isActive(pathname, item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href} className="animate-fade-up" style={{ animationDelay: `${60 * i}ms` }}>
                    <Link
                      href={item.href}
                      onClick={() => setOpen(false)}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-3 rounded-xl px-3 py-3 text-[1.05rem] transition-colors",
                        active ? "bg-primary-soft font-semibold text-primary" : "hover:bg-secondary",
                      )}
                    >
                      <Icon className="size-5" aria-hidden />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
          <p className="mt-auto border-t p-4 text-sm text-muted-foreground">
            জরুরি সাহায্যে জাতীয় হেল্পলাইন{" "}
            <a href="tel:333" className="font-semibold text-primary">
              ৩৩৩
            </a>
          </p>
        </SheetContent>
      </Sheet>
    </header>
  );
}
