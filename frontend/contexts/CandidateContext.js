"use client";

import { createContext, useContext, useState, useCallback } from "react";

const CandidateContext = createContext();

export function CandidateProvider({ children }) {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch("/candidates?page=1&page_size=50");
      if (!resp.ok) throw new Error(`API error ${resp.status}`);
      const data = await resp.json();
      setCandidates(data.candidates || []);
    } catch (e) {
      console.error("Failed to load candidates:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const stats = {
    total: candidates.length,
    enriched: candidates.filter((c) => c.llm_enriched).length,
  };

  return (
    <CandidateContext.Provider
      value={{ candidates, loading, loadCandidates, stats }}
    >
      {children}
    </CandidateContext.Provider>
  );
}

export function useCandidates() {
  const ctx = useContext(CandidateContext);
  if (!ctx)
    throw new Error("useCandidates must be used within CandidateProvider");
  return ctx;
}
