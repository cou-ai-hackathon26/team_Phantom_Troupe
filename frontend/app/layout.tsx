import type { Metadata, Viewport } from "next";
import { Hind_Siliguri } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const bangla = Hind_Siliguri({
  subsets: ["bengali", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-bangla",
  display: "swap",
});

export const metadata: Metadata = {
  title: "অধিকারAI — সরকারি নথি থেকে আপনার অধিকারের উত্তর",
  description: "জমি, জিডি, সামাজিক ভাতা ও শ্রমিক অধিকার নিয়ে প্রশ্ন বলুন বা লিখুন — উত্তর আসবে সরকারি নথির সূত্রসহ।",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f7" },
    { media: "(prefers-color-scheme: dark)", color: "#161513" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="bn" className={bangla.variable} suppressHydrationWarning>
      <head>
        {/* set the theme class before first paint, so dark mode never flashes light */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-dvh bg-glow bg-fixed font-sans">
        <a
          href="#question"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        >
          প্রশ্নের ঘরে যান
        </a>
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
