"use client";

import Link from "next/link";
import { useCandidates } from "@/contexts/CandidateContext";
import { useDrawer } from "@/contexts/DrawerContext";

function confidenceLevel(score) {
  if (score >= 0.9) return { cls: "very-high", label: "Very High" };
  if (score >= 0.75) return { cls: "high", label: "High" };
  if (score >= 0.6) return { cls: "medium", label: "Medium" };
  if (score >= 0.45) return { cls: "low", label: "Low" };
  return { cls: "very-low", label: "Very Low" };
}

function uniqueSources(provenance) {
  return [...new Set((provenance || []).map((p) => p.source))];
}

function sourceTagClass(source) {
  if (source.includes("csv")) return "csv";
  if (source.includes("github")) return "github";
  if (source.includes("llm")) return "llm";
  return "resume";
}

function sourceLabel(source) {
  return source
    .replace("recruiter_", "")
    .replace("_api", "")
    .replace("_llm", " LLM")
    .replace("_parsed", "");
}

function CandidateCard({ candidate, onClick }) {
  const c = candidate;
  const initials = (c.full_name || "?")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const conf = c.overall_confidence || 0;
  const level = confidenceLevel(conf);
  const skills = (c.skills || []).slice(0, 5);
  const extraCnt = (c.skills || []).length - skills.length;
  const sources = uniqueSources(c.provenance);

  return (
    <div className="candidate-card" onClick={onClick}>
      <div className="card-header">
        <div className="card-avatar">{initials}</div>
        <div className="card-meta">
          <div className="card-name">{c.full_name || "Unknown"}</div>
          <div className="card-headline">
            {c.headline || (c.emails && c.emails[0]) || "—"}
          </div>
        </div>
        <div className={`confidence-badge ${level.cls}`}>
          {(conf * 100).toFixed(0)}%
        </div>
      </div>

      <div className="card-skills">
        {skills.map((s, i) => (
          <span key={i} className="skill-chip">
            {s.name}
          </span>
        ))}
        {extraCnt > 0 && (
          <span className="skill-chip overflow">+{extraCnt}</span>
        )}
      </div>

      <div className="card-footer">
        <div className="card-sources">
          {sources.map((s, i) => (
            <span key={i} className={`source-tag ${sourceTagClass(s)}`}>
              {sourceLabel(s)}
            </span>
          ))}
        </div>
        {c.llm_enriched && (
          <span className="card-enrich-badge">✨ LLM Enriched</span>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { candidates, loading } = useCandidates();
  const { openDrawer } = useDrawer();

  if (loading && candidates.length === 0) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        Loading candidates…
      </div>
    );
  }

  if (!candidates.length) {
    return (
      <div className="candidates-grid">
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h3>No candidates yet</h3>
          <p>Upload a CSV or resume to get started</p>
          <Link href="/upload" className="btn-primary">
            Upload Now
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="candidates-grid">
      {candidates.map((c) => (
        <CandidateCard
          key={c.candidate_id}
          candidate={c}
          onClick={() => openDrawer(c)}
        />
      ))}
    </div>
  );
}
