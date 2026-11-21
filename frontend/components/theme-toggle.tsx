"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { applyTheme, currentTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme | null>(null); // null until mounted (server has no theme)

  useEffect(() => setTheme(currentTheme()), []);

  const toggle = () => {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  };

  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "হালকা রঙে দেখুন" : "গাঢ় রঙে দেখুন"}
      title={dark ? "হালকা রঙ" : "গাঢ় রঙ"}
      className={cn(
        "relative flex size-10 items-center justify-center overflow-hidden rounded-full border bg-card text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary",
        className,
      )}
    >
      <Sun
        className={cn("absolute size-[1.15rem] transition-all duration-300", dark ? "scale-0 -rotate-90 opacity-0" : "scale-100 rotate-0")}
        aria-hidden
      />
      <Moon
        className={cn("absolute size-[1.1rem] transition-all duration-300", dark ? "scale-100 rotate-0" : "scale-0 rotate-90 opacity-0")}
        aria-hidden
      />
    </button>
  );
}
