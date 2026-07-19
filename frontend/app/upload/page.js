"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useCandidates } from "@/contexts/CandidateContext";
import { useToast } from "@/contexts/ToastContext";

function DropZone({ id, accept, onFileSelect, selectedFile, hint }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) onFileSelect(file);
    },
    [onFileSelect]
  );

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleChange = useCallback(
    (e) => {
      if (e.target.files[0]) onFileSelect(e.target.files[0]);
    },
    [onFileSelect]
  );

  const zoneClasses = [
    "drop-zone",
    dragOver && "drag-over",
    selectedFile && "has-file",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <div
        className={zoneClasses}
        id={id}
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <svg viewBox="0 0 48 48" fill="none">
          <rect width="48" height="48" rx="12" fill="rgba(99,102,241,0.1)" />
          <path
            d="M24 14v20M14 24h20"
            stroke="#818cf8"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
        {selectedFile ? (
          <span className="file-name">📎 {selectedFile.name}</span>
        ) : (
          <>
            <p>
              Drop file here or <span className="link">browse</span>
            </p>
            <span className="drop-hint">{hint}</span>
          </>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={handleChange}
      />
    </>
  );
}

export default function UploadPage() {
  const router = useRouter();
  const { loadCandidates } = useCandidates();
  const { toast } = useToast();

  // CSV state
  const [csvFile, setCsvFile] = useState(null);
  const [csvLlmResolve, setCsvLlmResolve] = useState(false);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvResult, setCsvResult] = useState(null);

  // Resume state
  const [resumeFile, setResumeFile] = useState(null);
  const [resumeEnrich, setResumeEnrich] = useState(true);
  const [resumeUploading, setResumeUploading] = useState(false);
  const [resumeResult, setResumeResult] = useState(null);

  const handleCSVUpload = useCallback(async () => {
    if (!csvFile) return;
    setCsvUploading(true);
    setCsvResult(null);

    const form = new FormData();
    form.append("file", csvFile);
    form.append("enable_llm", csvLlmResolve);

    try {
      const resp = await fetch("/candidates/from-csv", {
        method: "POST",
        body: form,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Upload failed");
      setCsvResult({
        type: "success",
        text: `✓ Imported ${data.candidate_ids.length} candidates`,
      });
      toast(
        `CSV imported: ${data.candidate_ids.length} candidates`,
        "success"
      );
      await loadCandidates();
      setTimeout(() => router.push("/"), 800);
    } catch (e) {
      setCsvResult({ type: "error", text: `✗ ${e.message}` });
      toast(`CSV upload failed: ${e.message}`, "error");
    } finally {
      setCsvUploading(false);
    }
  }, [csvFile, csvLlmResolve, loadCandidates, router, toast]);

  const handleResumeUpload = useCallback(async () => {
    if (!resumeFile) return;
    setResumeUploading(true);
    setResumeResult(null);

    const form = new FormData();
    form.append("file", resumeFile);
    form.append("enrich_with_llm", resumeEnrich);

    try {
      const resp = await fetch("/candidates/from-resume", {
        method: "POST",
        body: form,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Upload failed");
      setResumeResult({
        type: "success",
        text: `✓ Profile created: ${data.candidate?.full_name || data.candidate_id}`,
      });
      toast(
        `Resume processed: ${data.candidate?.full_name || "unknown"}`,
        "success"
      );
      await loadCandidates();
      setTimeout(() => router.push("/"), 800);
    } catch (e) {
      setResumeResult({ type: "error", text: `✗ ${e.message}` });
      toast(`Resume upload failed: ${e.message}`, "error");
    } finally {
      setResumeUploading(false);
    }
  }, [resumeFile, resumeEnrich, loadCandidates, router, toast]);

  return (
    <div className="upload-grid">
      {/* CSV Upload Card */}
      <div className="upload-card glass-card">
        <div className="upload-card-icon">📊</div>
        <h3>Recruiter CSV</h3>
        <p>
          Upload a structured CSV with candidate data (name, email, phone,
          skills…)
        </p>

        <DropZone
          id="drop-csv"
          accept=".csv"
          selectedFile={csvFile}
          onFileSelect={setCsvFile}
          hint="Supports recruiter export format"
        />

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={csvLlmResolve}
            onChange={(e) => setCsvLlmResolve(e.target.checked)}
          />
          <span>Enable LLM conflict resolution</span>
        </label>

        <button
          className="btn-primary"
          disabled={!csvFile || csvUploading}
          onClick={handleCSVUpload}
        >
          <span className="btn-label">
            {csvUploading ? "Uploading…" : "Upload CSV"}
          </span>
          {csvUploading && <span className="btn-spinner">⟳</span>}
        </button>

        {csvResult && (
          <div className={`upload-result ${csvResult.type}`}>
            {csvResult.text}
          </div>
        )}
      </div>

      {/* Resume Upload Card */}
      <div className="upload-card glass-card">
        <div className="upload-card-icon">📄</div>
        <h3>Resume File</h3>
        <p>
          Upload a single resume (PDF, DOCX, or TXT). Gemini will extract
          structured data.
        </p>

        <DropZone
          id="drop-resume"
          accept=".pdf,.docx,.txt"
          selectedFile={resumeFile}
          onFileSelect={setResumeFile}
          hint="PDF · DOCX · TXT"
        />

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={resumeEnrich}
            onChange={(e) => setResumeEnrich(e.target.checked)}
          />
          <span>Enrich with Gemini LLM</span>
        </label>

        <button
          className="btn-primary"
          disabled={!resumeFile || resumeUploading}
          onClick={handleResumeUpload}
        >
          <span className="btn-label">
            {resumeUploading ? "Uploading…" : "Upload Resume"}
          </span>
          {resumeUploading && <span className="btn-spinner">⟳</span>}
        </button>

        {resumeResult && (
          <div className={`upload-result ${resumeResult.type}`}>
            {resumeResult.text}
          </div>
        )}
      </div>
    </div>
  );
}
