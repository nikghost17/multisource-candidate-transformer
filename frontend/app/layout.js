import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

import { ToastProvider } from "@/contexts/ToastContext";
import { CandidateProvider } from "@/contexts/CandidateContext";
import { DrawerProvider } from "@/contexts/DrawerContext";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import CandidateDrawer from "@/components/CandidateDrawer";
import AppShell from "@/components/AppShell";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["300", "400", "500", "600", "700", "800"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata = {
  title: "CandidateIQ — Candidate Intelligence Platform",
  description:
    "AI-powered multi-source candidate profile enrichment with RAG and Gemini LLM.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body style={{ fontFamily: "var(--font-inter), sans-serif" }}>
        <ToastProvider>
          <CandidateProvider>
            <DrawerProvider>
              <AppShell>{children}</AppShell>
              <CandidateDrawer />
            </DrawerProvider>
          </CandidateProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
