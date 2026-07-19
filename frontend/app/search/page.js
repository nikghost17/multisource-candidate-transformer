"use client";

import { useState, useCallback } from "react";
import { useDrawer } from "@/contexts/DrawerContext";
import { useToast } from "@/contexts/ToastContext";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const { openDrawer } = useDrawer();
  const { toast } = useToast();

  const runSearch = useCallback(
    async (q) => {
      const searchQuery = q || query;
      if (!searchQuery.trim()) return;

      setQuery(searchQuery);
      setSearching(true);
      setResults(null);

      try {
        const resp = await fetch(
          `/candidates/search?q=${encodeURIComponent(searchQuery)}&top_k=10`
        );
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "Search failed");

        setResults(data.results || []);
      } catch (e) {
        toast(`Search failed: ${e.message}`, "error");
        setResults([]);
      } finally {
        setSearching(false);
      }
    },
    [query, toast]
  );

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === "Enter") runSearch();
    },
    [runSearch]
  );

  const quickSearches = [
    { label: "ML Engineer India", query: "machine learning engineer India" },
    { label: "Full Stack React/Node", query: "full stack developer react node" },
    { label: "Senior Data Scientist", query: "senior data scientist python pytorch" },
    { label: "DevOps + K8s", query: "devops kubernetes AWS" },
  ];

  return (
    <div className="search-container glass-card">
      <h3>Semantic Search</h3>
      <p>Search across all indexed resumes using natural language.</p>

      <div className="search-input-row">
        <input
          type="text"
          id="search-input"
          placeholder="e.g. Python engineer with ML experience and AWS skills…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="btn-primary"
          onClick={() => runSearch()}
          disabled={searching}
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </div>

      <div className="search-chips">
        {quickSearches.map((qs, i) => (
          <button
            key={i}
            className="chip"
            onClick={() => runSearch(qs.query)}
          >
            {qs.label}
          </button>
        ))}
      </div>

      <div className="search-results">
        {searching && (
          <div className="loading-state">
            <div className="loading-spinner" />
            Searching…
          </div>
        )}

        {results !== null && !searching && results.length === 0 && (
          <p style={{ color: "var(--text-muted)" }}>No results found.</p>
        )}

        {results !== null &&
          !searching &&
          results.map((r, i) => {
            const c = r.candidate;
            const initials = (c.full_name || "?")
              .split(" ")
              .map((w) => w[0])
              .join("")
              .slice(0, 2)
              .toUpperCase();

            return (
              <div
                key={i}
                className="search-result-card"
                onClick={() => openDrawer(c)}
              >
                <div
                  className="card-avatar"
                  style={{ width: 36, height: 36, fontSize: 13 }}
                >
                  {initials}
                </div>
                <div className="search-result-body">
                  <div className="search-result-name">
                    {c.full_name || "Unknown"}
                  </div>
                  <div className="search-result-chunk">
                    {r.matched_chunk || ""}
                  </div>
                </div>
                <div className="search-result-score">
                  {(r.relevance_score * 100).toFixed(0)}%
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}
