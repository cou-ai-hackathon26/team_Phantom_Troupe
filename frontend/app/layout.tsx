import type { Metadata, Viewport } from "next";
import { Hind_Siliguri } from "next/font/google";
import "./globals.css";

const bangla = Hind_Siliguri({
  subsets: ["bengali", "latin"],
  weight: ["400", "600"],
  variable: "--font-bangla",
  display: "swap",
});

export const metadata: Metadata = {
  title: "অধিকারAI — সরকারি নথি থেকে আপনার অধিকারের উত্তর",
  description: "জমি, জিডি, সামাজিক ভাতা ও শ্রমিক অধিকার নিয়ে প্রশ্ন বলুন বা লিখুন — উত্তর আসবে সরকারি নথির সূত্রসহ।",
};

export const viewport: Viewport = {
  themeColor: "#0b6e4f",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="bn" className={bangla.variable}>
      <body className="min-h-dvh font-sans">{children}</body>
    </html>
  );
}
