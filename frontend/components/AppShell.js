"use client";

import { useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import { useCandidates } from "@/contexts/CandidateContext";

export default function AppShell({ children }) {
  const { loadCandidates } = useCandidates();

  useEffect(() => {
    loadCandidates();
  }, [loadCandidates]);

  return (
    <>
      <Sidebar />
      <main className="main-content">
        <Topbar />
        <div className="page-content">{children}</div>
      </main>
    </>
  );
}
