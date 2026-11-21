"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { House, Info, Menu, ShieldUser } from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "হোম", icon: House },
  { href: "/about", label: "কীভাবে কাজ করে", icon: Info },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("text-lg font-bold tracking-tight sm:text-xl", className)}>
      অধিকার<span className="text-primary">AI</span>
    </span>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="glass sticky top-0 z-30 border-b">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
        <Link href="/" className="group flex items-center gap-2.5" aria-label="অধিকারAI — হোম">
          <BrandMark className="transition-transform duration-300 group-hover:scale-105" />
          <Wordmark />
        </Link>

        <div className="flex items-center gap-2">
          <nav aria-label="প্রধান মেনু" className="hidden md:block">
            <ul className="flex items-center gap-1 text-[0.95rem]">
              {NAV.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "block rounded-full px-4 py-2 transition-colors",
                        active ? "bg-primary-soft font-semibold text-primary" : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
          <ThemeToggle />
          <Link
            href="/admin"
            aria-label="অ্যাডমিন"
            title="অ্যাডমিন"
            className={cn(
              "hidden size-10 items-center justify-center rounded-full border bg-card text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary md:flex",
              pathname.startsWith("/admin") && "border-primary/40 text-primary",
            )}
          >
            <ShieldUser className="size-[1.15rem]" aria-hidden />
          </Link>
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label="মেনু খুলুন"
            aria-expanded={open}
            className="flex size-10 items-center justify-center rounded-full border bg-card md:hidden"
          >
            <Menu className="size-5" aria-hidden />
          </button>
        </div>
      </div>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-[82%] max-w-xs gap-0 p-0">
          <SheetHeader className="border-b p-4">
            <SheetTitle className="flex items-center gap-2.5 text-left">
              <BrandMark className="size-8" />
              <Wordmark />
            </SheetTitle>
            <SheetDescription className="sr-only">মেনু</SheetDescription>
          </SheetHeader>
          <nav aria-label="মোবাইল মেনু" className="p-3">
            <ul className="space-y-1">
              {NAV.map((item) => {
                const active = isActive(pathname, item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
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
          <div className="mt-auto space-y-3 border-t p-4 text-sm">
            <p className="text-muted-foreground">
              জরুরি সাহায্যে জাতীয় হেল্পলাইন{" "}
              <a href="tel:333" className="font-semibold text-primary">
                ৩৩৩
              </a>
            </p>
            <Link href="/admin" onClick={() => setOpen(false)} className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground">
              <ShieldUser className="size-4" aria-hidden /> অ্যাডমিন
            </Link>
          </div>
        </SheetContent>
      </Sheet>
    </header>
  );
}
