"use client";

import { useState, useEffect, useCallback } from "react";
import { useDrawer } from "@/contexts/DrawerContext";
import { useCandidates } from "@/contexts/CandidateContext";
import { useToast } from "@/contexts/ToastContext";

function esc(str) {
  if (str == null) return "";
  return String(str);
}

function locationStr(loc) {
  if (!loc) return "—";
  return [loc.city, loc.region, loc.country].filter(Boolean).join(", ") || "—";
}

function confidenceLevel(score) {
  if (score >= 0.9) return { cls: "very-high", label: "Very High", color: "#16a34a" };
  if (score >= 0.75) return { cls: "high", label: "High", color: "#22c55e" };
  if (score >= 0.6) return { cls: "medium", label: "Medium", color: "#ca8a04" };
  if (score >= 0.45) return { cls: "low", label: "Low", color: "#ea580c" };
  return { cls: "very-low", label: "Very Low", color: "#dc2626" };
}

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span className="info-key">{label}</span>
      <span className="info-value" dangerouslySetInnerHTML={{ __html: value || "—" }} />
    </div>
  );
}

// ─── Profile Tab ────────────────────────────────────────────────
function ProfileTab({ candidate: c }) {
  if (!c) return null;

  return (
    <>
      {c.llm_summary && (
        <div className="profile-section">
          <div className="profile-section-title">✨ AI Summary</div>
          <div className="llm-summary">{esc(c.llm_summary)}</div>
        </div>
      )}

      <div className="profile-section">
        <div className="profile-section-title">Contact</div>
        <InfoRow label="Emails" value={(c.emails || []).join(", ") || "—"} />
        <InfoRow label="Phones" value={(c.phones || []).join(", ") || "—"} />
        <InfoRow label="Location" value={locationStr(c.location)} />
        <InfoRow
          label="YoE"
          value={c.years_experience != null ? `${c.years_experience} years` : "—"}
        />
        {c.links?.linkedin && (
          <InfoRow
            label="LinkedIn"
            value={`<a href="${esc(c.links.linkedin)}" target="_blank" rel="noopener">${esc(c.links.linkedin)}</a>`}
          />
        )}
        {c.links?.github && (
          <InfoRow
            label="GitHub"
            value={`<a href="${esc(c.links.github)}" target="_blank" rel="noopener">${esc(c.links.github)}</a>`}
          />
        )}
        {c.links?.portfolio && (
          <InfoRow
            label="Portfolio"
            value={`<a href="${esc(c.links.portfolio)}" target="_blank" rel="noopener">${esc(c.links.portfolio)}</a>`}
          />
        )}
      </div>

      {c.skills && c.skills.length > 0 && (
        <div className="profile-section">
          <div className="profile-section-title">Skills ({c.skills.length})</div>
          <div className="skills-list">
            {c.skills.map((s, i) => (
              <span key={i} className="skill-tag">
                {esc(s.name)}
              </span>
            ))}
          </div>
        </div>
      )}

      {c.experience && c.experience.length > 0 && (
        <div className="profile-section">
          <div className="profile-section-title">Experience</div>
          {c.experience.map((e, i) => (
            <div key={i} className="exp-item">
              <div className="exp-company">{esc(e.company)}</div>
              <div className="exp-title">{esc(e.title)}</div>
              {e.start && (
                <div className="exp-dates">
                  {esc(e.start)} → {e.end ? esc(e.end) : "Present"}
                </div>
              )}
              {e.summary && <div className="exp-summary">{esc(e.summary)}</div>}
            </div>
          ))}
        </div>
      )}

      {c.education && c.education.length > 0 && (
        <div className="profile-section">
          <div className="profile-section-title">Education</div>
          {c.education.map((e, i) => (
            <div key={i} className="edu-item">
              <div className="exp-company">{esc(e.institution)}</div>
              {e.degree && (
                <div className="exp-title">
                  {esc(e.degree)}
                  {e.field_of_study ? ` · ${esc(e.field_of_study)}` : ""}
                </div>
              )}
              {e.end_year && (
                <div className="exp-dates">Graduated {esc(String(e.end_year))}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

// ─── Confidence Tab ─────────────────────────────────────────────
function ConfidenceTab({ candidateId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!candidateId) return;
    setData(null);
    setError(false);

    fetch(`/candidates/${candidateId}/confidence`)
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then(setData)
      .catch(() => setError(true));
  }, [candidateId]);

  if (error) return <p style={{ color: "var(--red)" }}>Failed to load confidence data.</p>;
  if (!data) return <p style={{ color: "var(--text-muted)", padding: "8px 0" }}>Loading…</p>;

  const level = data.overall_level || {};
  const presentFields = (data.fields || []).filter((f) => f.present);
  const missingFields = (data.fields || []).filter((f) => !f.present);

  return (
    <>
      <div className="confidence-overall">
        <div className="score" style={{ color: level.color }}>
          {((data.overall_confidence || 0) * 100).toFixed(0)}%
        </div>
        <div className="level" style={{ color: level.color }}>
          {level.label || ""}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
          Sources: {(data.source_summary || []).join(" · ")}
        </div>
      </div>

      {presentFields.map((f, i) => {
        const pct = Math.round(f.confidence * 100);
        const color = f.level?.color || "#6366f1";
        return (
          <div key={i} className="field-bar-item">
            <div className="field-bar-header">
              <span className="field-bar-name">{esc(f.field)}</span>
              <span className="field-bar-score">{pct}%</span>
            </div>
            <div className="field-bar-track">
              <div
                className="field-bar-fill"
                style={{ width: `${pct}%`, background: color }}
              />
            </div>
            <div className="field-bar-meta">
              {esc(f.source)} · {esc(f.method)}
            </div>
          </div>
        );
      })}

      {missingFields.length > 0 && (
        <div style={{ marginTop: 16, fontSize: 12, color: "var(--text-muted)" }}>
          Missing fields: {missingFields.map((f) => esc(f.field)).join(", ")}
        </div>
      )}
    </>
  );
}

// ─── Provenance Tab ─────────────────────────────────────────────
function ProvenanceTab({ provenance }) {
  if (!provenance || !provenance.length) {
    return <p style={{ color: "var(--text-muted)" }}>No provenance data available.</p>;
  }

  return provenance.map((p, i) => (
    <div key={i} className="prov-item">
      <div className="prov-field">{esc(p.field_name)}</div>
      <div className="prov-source">
        {esc(p.source)} · conf: {(p.confidence * 100).toFixed(0)}%
      </div>
      <div className="prov-method">{esc(p.method)}</div>
    </div>
  ));
}

// ─── Main Drawer Component ──────────────────────────────────────
export default function CandidateDrawer() {
  const { isOpen, activeCandidate, closeDrawer, openDrawer } = useDrawer();
  const { loadCandidates, candidates } = useCandidates();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState("profile");
  const [enriching, setEnriching] = useState(false);

  // Reset to profile tab when candidate changes
  useEffect(() => {
    if (activeCandidate) setActiveTab("profile");
  }, [activeCandidate]);

  const c = activeCandidate;
  const initials = c
    ? (c.full_name || "?")
        .split(" ")
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : "?";

  const handleEnrich = useCallback(async () => {
    if (!c) return;
    setEnriching(true);
    try {
      const resp = await fetch(`/candidates/${c.candidate_id}/enrich`, {
        method: "POST",
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Enrichment failed");
      toast("Candidate enriched with Gemini! ✨", "success");
      await loadCandidates();
    } catch (e) {
      toast(`Enrichment failed: ${e.message}`, "error");
    } finally {
      setEnriching(false);
    }
  }, [c, loadCandidates, toast]);

  // Re-open with fresh data after enrichment
  useEffect(() => {
    if (!enriching && c && candidates.length) {
      const fresh = candidates.find((x) => x.candidate_id === c.candidate_id);
      if (fresh && fresh !== c) {
        openDrawer(fresh);
      }
    }
  }, [candidates, enriching]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = useCallback(async () => {
    if (!c) return;
    if (
      !window.confirm(
        `Delete candidate "${c.full_name || c.candidate_id}"? This cannot be undone.`
      )
    )
      return;
    try {
      const resp = await fetch(`/candidates/${c.candidate_id}`, {
        method: "DELETE",
      });
      if (!resp.ok) throw new Error();
      toast("Candidate deleted.", "info");
      closeDrawer();
      await loadCandidates();
    } catch {
      toast("Failed to delete candidate.", "error");
    }
  }, [c, closeDrawer, loadCandidates, toast]);

  const tabs = [
    { key: "profile", label: "Profile" },
    { key: "confidence", label: "Confidence" },
    { key: "provenance", label: "Provenance" },
  ];

  return (
    <>
      <div
        className={`drawer-overlay ${isOpen ? "active" : ""}`}
        onClick={closeDrawer}
      />
      <aside className={`detail-drawer ${isOpen ? "open" : ""}`}>
        <div className="drawer-header">
          <div className="drawer-avatar">{initials}</div>
          <div className="drawer-title">
            <h2>{c?.full_name || "—"}</h2>
            <p>{c?.headline || c?.emails?.[0] || "—"}</p>
          </div>
          <button className="drawer-close" onClick={closeDrawer}>
            ✕
          </button>
        </div>

        <div className="drawer-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              className={`tab-btn ${activeTab === tab.key ? "active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="drawer-body">
          <div
            className={`tab-panel ${activeTab === "profile" ? "active" : ""}`}
          >
            <ProfileTab candidate={c} />
          </div>
          <div
            className={`tab-panel ${activeTab === "confidence" ? "active" : ""}`}
          >
            {activeTab === "confidence" && c && (
              <ConfidenceTab candidateId={c.candidate_id} />
            )}
          </div>
          <div
            className={`tab-panel ${activeTab === "provenance" ? "active" : ""}`}
          >
            {activeTab === "provenance" && (
              <ProvenanceTab provenance={c?.provenance} />
            )}
          </div>
        </div>

        <div className="drawer-footer">
          <button
            className="btn-outline"
            onClick={handleEnrich}
            disabled={c?.llm_enriched || enriching}
          >
            {enriching
              ? "⟳ Enriching…"
              : c?.llm_enriched
              ? "✓ Already Enriched"
              : "✨ Enrich with Gemini"}
          </button>
          <button className="btn-danger" onClick={handleDelete}>
            🗑 Delete
          </button>
        </div>
      </aside>
    </>
  );
}
