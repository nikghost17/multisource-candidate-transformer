/* =============================================================
   Candidate Intelligence Platform — Frontend JavaScript
   Communicates with the FastAPI backend at /api/...
   ============================================================= */

// Auto-detect API base from current page URL — works on any port
const API_BASE = window.location.origin;


// ─── State ───────────────────────────────────────────────────
let _candidates    = [];
let _activeCandidate = null;

// ─── DOM refs ─────────────────────────────────────────────────
const grid         = document.getElementById('candidates-grid');
const emptyState   = document.getElementById('empty-state');
const drawer       = document.getElementById('detail-drawer');
const overlay      = document.getElementById('drawer-overlay');
const toastCont    = document.getElementById('toast-container');

// ─── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();
  setupFileUploads();
  setupDrawer();
  setupSearch();
  loadCandidates();
});

// ─── Navigation ───────────────────────────────────────────────
function setupNavigation() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });
  document.getElementById('refresh-btn').addEventListener('click', loadCandidates);
}

window.switchView = function(view) {
  // Update nav
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  // Update views
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${view}`));

  const titles = {
    dashboard: ['Candidate Dashboard', 'All ingested candidate profiles'],
    upload:    ['Upload Data', 'Import candidates from CSV or resume files'],
    search:    ['Semantic Search', 'Find candidates with natural language queries'],
  };
  if (titles[view]) {
    document.getElementById('page-title').textContent    = titles[view][0];
    document.getElementById('page-subtitle').textContent = titles[view][1];
  }
};

// ─── Load Candidates ──────────────────────────────────────────
async function loadCandidates() {
  try {
    const resp = await fetch(`${API_BASE}/candidates?page=1&page_size=50`);
    if (!resp.ok) throw new Error(`API error ${resp.status}`);
    const data = await resp.json();
    _candidates = data.candidates || [];
    renderGrid(_candidates);
    updateSidebarStats();
  } catch (e) {
    console.error('Failed to load candidates:', e);
    toast('Could not reach the API. Is the server running?', 'error');
  }
}

// ─── Render Grid ──────────────────────────────────────────────
function renderGrid(candidates) {
  if (!candidates.length) {
    grid.innerHTML = '';
    grid.appendChild(emptyState);
    emptyState.style.display = '';
    return;
  }
  emptyState.style.display = 'none';
  grid.innerHTML = candidates.map(c => candidateCardHTML(c)).join('');
  grid.querySelectorAll('.candidate-card').forEach((card, i) => {
    card.addEventListener('click', () => openDrawer(candidates[i]));
  });
}

function candidateCardHTML(c) {
  const initials = (c.full_name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  const conf     = c.overall_confidence || 0;
  const level    = confidenceLevel(conf);
  const skills   = (c.skills || []).slice(0, 5);
  const extraCnt = (c.skills || []).length - skills.length;
  const sources  = uniqueSources(c.provenance || []);

  return `
    <div class="candidate-card" data-id="${c.candidate_id}">
      <div class="card-header">
        <div class="card-avatar">${initials}</div>
        <div class="card-meta">
          <div class="card-name">${esc(c.full_name || 'Unknown')}</div>
          <div class="card-headline">${esc(c.headline || (c.emails && c.emails[0]) || '—')}</div>
        </div>
        <div class="confidence-badge ${level.cls}">${(conf * 100).toFixed(0)}%</div>
      </div>
      <div class="card-skills">
        ${skills.map(s => `<span class="skill-chip">${esc(s.name)}</span>`).join('')}
        ${extraCnt > 0 ? `<span class="skill-chip overflow">+${extraCnt}</span>` : ''}
      </div>
      <div class="card-footer">
        <div class="card-sources">
          ${sources.map(s => sourceTagHTML(s)).join('')}
        </div>
        ${c.llm_enriched ? '<span class="card-enrich-badge">✨ LLM Enriched</span>' : ''}
      </div>
    </div>
  `;
}

function sourceTagHTML(source) {
  const cls = source.includes('csv') ? 'csv' : source.includes('github') ? 'github' : source.includes('llm') ? 'llm' : 'resume';
  const label = source.replace('recruiter_', '').replace('_api', '').replace('_llm', ' LLM').replace('_parsed', '');
  return `<span class="source-tag ${cls}">${esc(label)}</span>`;
}

function uniqueSources(provenance) {
  return [...new Set(provenance.map(p => p.source))];
}

function updateSidebarStats() {
  document.getElementById('stat-total').textContent    = _candidates.length;
  document.getElementById('stat-enriched').textContent = _candidates.filter(c => c.llm_enriched).length;
}

// ─── Confidence helpers ───────────────────────────────────────
function confidenceLevel(score) {
  if (score >= 0.90) return { cls: 'very-high', label: 'Very High', color: '#22c55e' };
  if (score >= 0.75) return { cls: 'high',      label: 'High',      color: '#86efac' };
  if (score >= 0.60) return { cls: 'medium',    label: 'Medium',    color: '#eab308' };
  if (score >= 0.45) return { cls: 'low',       label: 'Low',       color: '#f97316' };
  return              { cls: 'very-low', label: 'Very Low', color: '#ef4444' };
}

// ─── Drawer ───────────────────────────────────────────────────
function setupDrawer() {
  overlay.addEventListener('click', closeDrawer);
  document.getElementById('drawer-close').addEventListener('click', closeDrawer);

  // Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });

  document.getElementById('drawer-enrich-btn').addEventListener('click', enrichActiveCandidate);
  document.getElementById('drawer-delete-btn').addEventListener('click', deleteActiveCandidate);
}

async function openDrawer(candidate) {
  _activeCandidate = candidate;
  drawer.classList.add('open');
  overlay.classList.add('active');
  document.body.style.overflow = 'hidden';

  renderDrawerHeader(candidate);
  renderProfileTab(candidate);

  // Reset to profile tab
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelector('.tab-btn[data-tab="profile"]').classList.add('active');
  document.getElementById('tab-profile').classList.add('active');

  // Load confidence breakdown async
  loadConfidenceTab(candidate.candidate_id);
  renderProvenanceTab(candidate);

  // Update enrich button state
  const enrichBtn = document.getElementById('drawer-enrich-btn');
  enrichBtn.disabled = candidate.llm_enriched;
  enrichBtn.textContent = candidate.llm_enriched ? '✓ Already Enriched' : '✨ Enrich with Gemini';
}

function closeDrawer() {
  drawer.classList.remove('open');
  overlay.classList.remove('active');
  document.body.style.overflow = '';
  _activeCandidate = null;
}

function renderDrawerHeader(c) {
  const initials = (c.full_name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  document.getElementById('drawer-avatar').textContent  = initials;
  document.getElementById('drawer-name').textContent    = c.full_name || 'Unknown';
  document.getElementById('drawer-headline').textContent = c.headline || c.emails?.[0] || '—';
}

function renderProfileTab(c) {
  const panel = document.getElementById('tab-profile');
  let html = '';

  // LLM Summary
  if (c.llm_summary) {
    html += `
      <div class="profile-section">
        <div class="profile-section-title">✨ AI Summary</div>
        <div class="llm-summary">${esc(c.llm_summary)}</div>
      </div>`;
  }

  // Contact info
  html += `<div class="profile-section"><div class="profile-section-title">Contact</div>`;
  html += infoRow('Emails',    (c.emails || []).join(', ') || '—');
  html += infoRow('Phones',    (c.phones || []).join(', ') || '—');
  html += infoRow('Location',  locationStr(c.location));
  html += infoRow('YoE',       c.years_experience != null ? `${c.years_experience} years` : '—');
  if (c.links) {
    if (c.links.linkedin)  html += infoRow('LinkedIn',  `<a href="${esc(c.links.linkedin)}" target="_blank">${esc(c.links.linkedin)}</a>`);
    if (c.links.github)    html += infoRow('GitHub',    `<a href="${esc(c.links.github)}" target="_blank">${esc(c.links.github)}</a>`);
    if (c.links.portfolio) html += infoRow('Portfolio', `<a href="${esc(c.links.portfolio)}" target="_blank">${esc(c.links.portfolio)}</a>`);
  }
  html += `</div>`;

  // Skills
  if (c.skills && c.skills.length) {
    html += `<div class="profile-section"><div class="profile-section-title">Skills (${c.skills.length})</div>`;
    html += `<div class="skills-list">` + c.skills.map(s => `<span class="skill-tag">${esc(s.name)}</span>`).join('') + `</div></div>`;
  }

  // Experience
  if (c.experience && c.experience.length) {
    html += `<div class="profile-section"><div class="profile-section-title">Experience</div>`;
    html += c.experience.map(e => `
      <div class="exp-item">
        <div class="exp-company">${esc(e.company)}</div>
        <div class="exp-title">${esc(e.title)}</div>
        ${e.start ? `<div class="exp-dates">${esc(e.start)} → ${e.end ? esc(e.end) : 'Present'}</div>` : ''}
        ${e.summary ? `<div class="exp-summary">${esc(e.summary)}</div>` : ''}
      </div>`).join('');
    html += `</div>`;
  }

  // Education
  if (c.education && c.education.length) {
    html += `<div class="profile-section"><div class="profile-section-title">Education</div>`;
    html += c.education.map(e => `
      <div class="edu-item">
        <div class="exp-company">${esc(e.institution)}</div>
        ${e.degree ? `<div class="exp-title">${esc(e.degree)}${e.field_of_study ? ' · ' + esc(e.field_of_study) : ''}</div>` : ''}
        ${e.end_year ? `<div class="exp-dates">Graduated ${esc(String(e.end_year))}</div>` : ''}
      </div>`).join('');
    html += `</div>`;
  }

  panel.innerHTML = html;
}

async function loadConfidenceTab(candidateId) {
  const panel = document.getElementById('tab-confidence');
  panel.innerHTML = '<p style="color:var(--text-muted);padding:8px 0">Loading…</p>';

  try {
    const resp = await fetch(`${API_BASE}/candidates/${candidateId}/confidence`);
    if (!resp.ok) throw new Error();
    const data = await resp.json();
    renderConfidenceTab(data);
  } catch {
    panel.innerHTML = '<p style="color:var(--red)">Failed to load confidence data.</p>';
  }
}

function renderConfidenceTab(data) {
  const panel = document.getElementById('tab-confidence');
  const level = data.overall_level || {};
  let html = `
    <div class="confidence-overall">
      <div class="score" style="color:${level.color}">${((data.overall_confidence || 0) * 100).toFixed(0)}%</div>
      <div class="level" style="color:${level.color}">${level.label || ''}</div>
      <div style="font-size:11px;color:var(--text-muted);margin-top:6px">Sources: ${(data.source_summary || []).join(' · ')}</div>
    </div>`;

  const fields = (data.fields || []).filter(f => f.present);
  fields.forEach(f => {
    const pct   = Math.round(f.confidence * 100);
    const color = f.level?.color || '#6366f1';
    html += `
      <div class="field-bar-item">
        <div class="field-bar-header">
          <span class="field-bar-name">${esc(f.field)}</span>
          <span class="field-bar-score">${pct}%</span>
        </div>
        <div class="field-bar-track">
          <div class="field-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <div class="field-bar-meta">${esc(f.source)} · ${esc(f.method)}</div>
      </div>`;
  });

  // Missing fields
  const missing = (data.fields || []).filter(f => !f.present);
  if (missing.length) {
    html += `<div style="margin-top:16px;font-size:12px;color:var(--text-muted)">Missing fields: ${missing.map(f => esc(f.field)).join(', ')}</div>`;
  }

  panel.innerHTML = html;
}

function renderProvenanceTab(c) {
  const panel = document.getElementById('tab-provenance');
  const provenance = c.provenance || [];
  if (!provenance.length) {
    panel.innerHTML = '<p style="color:var(--text-muted)">No provenance data available.</p>';
    return;
  }
  panel.innerHTML = provenance.map(p => `
    <div class="prov-item">
      <div class="prov-field">${esc(p.field_name)}</div>
      <div class="prov-source">${esc(p.source)} · conf: ${(p.confidence * 100).toFixed(0)}%</div>
      <div class="prov-method">${esc(p.method)}</div>
    </div>`).join('');
}

// ─── Enrich + Delete ──────────────────────────────────────────
async function enrichActiveCandidate() {
  if (!_activeCandidate) return;
  const btn = document.getElementById('drawer-enrich-btn');
  btn.disabled = true;
  btn.textContent = '⟳ Enriching…';

  try {
    const resp = await fetch(`${API_BASE}/candidates/${_activeCandidate.candidate_id}/enrich`, { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Enrichment failed');
    toast('Candidate enriched with Gemini! ✨', 'success');
    await loadCandidates();
    // Re-open with fresh data
    const fresh = _candidates.find(c => c.candidate_id === _activeCandidate.candidate_id);
    if (fresh) openDrawer(fresh);
  } catch (e) {
    toast(`Enrichment failed: ${e.message}`, 'error');
    btn.disabled = false;
    btn.textContent = '✨ Enrich with Gemini';
  }
}

async function deleteActiveCandidate() {
  if (!_activeCandidate) return;
  if (!confirm(`Delete candidate "${_activeCandidate.full_name || _activeCandidate.candidate_id}"? This cannot be undone.`)) return;

  try {
    const resp = await fetch(`${API_BASE}/candidates/${_activeCandidate.candidate_id}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error();
    toast('Candidate deleted.', 'info');
    closeDrawer();
    await loadCandidates();
  } catch {
    toast('Failed to delete candidate.', 'error');
  }
}

// ─── File Uploads ─────────────────────────────────────────────
function setupFileUploads() {
  setupDropZone('drop-csv',    'input-csv',    handleCSVUpload);
  setupDropZone('drop-resume', 'input-resume', handleResumeUpload);

  document.getElementById('input-csv').addEventListener('change', e => {
    if (e.target.files[0]) markDropZoneFile('drop-csv', e.target.files[0].name);
  });
  document.getElementById('input-resume').addEventListener('change', e => {
    if (e.target.files[0]) markDropZoneFile('drop-resume', e.target.files[0].name);
  });

  document.getElementById('btn-upload-csv').addEventListener('click', handleCSVUpload);
  document.getElementById('btn-upload-resume').addEventListener('click', handleResumeUpload);
}

function setupDropZone(zoneId, inputId, handler) {
  const zone  = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const btn   = document.getElementById(`btn-upload-${zoneId.replace('drop-', '')}`);

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave',  () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) {
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      markDropZoneFile(zoneId, file.name);
    }
  });

  input.addEventListener('change', () => {
    btn.disabled = !input.files.length;
  });
}

function markDropZoneFile(zoneId, name) {
  const zone = document.getElementById(zoneId);
  zone.classList.add('has-file');
  const hint = zone.querySelector('.drop-hint, .file-name');
  if (hint) { hint.className = 'file-name'; hint.textContent = `📎 ${name}`; }
  const inputId = zoneId.replace('drop-', 'input-');
  document.getElementById(`btn-upload-${zoneId.replace('drop-', '')}`).disabled = false;
}

function setUploading(type, state) {
  const btn     = document.getElementById(`btn-upload-${type}`);
  const label   = btn.querySelector('.btn-label');
  const spinner = btn.querySelector('.btn-spinner');
  btn.disabled  = state;
  label.textContent = state ? 'Uploading…' : (type === 'csv' ? 'Upload CSV' : 'Upload Resume');
  spinner.classList.toggle('hidden', !state);
}

async function handleCSVUpload() {
  const input = document.getElementById('input-csv');
  const file  = input.files[0];
  if (!file) return;

  const enableLLM = document.getElementById('csv-llm-resolve').checked;
  const resultEl  = document.getElementById('csv-result');
  setUploading('csv', true);
  resultEl.className = 'upload-result';
  resultEl.textContent = '';

  const form = new FormData();
  form.append('file', file);
  form.append('enable_llm', enableLLM);

  try {
    const resp = await fetch(`${API_BASE}/candidates/from-csv`, { method: 'POST', body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Upload failed');
    resultEl.className = 'upload-result success';
    resultEl.textContent = `✓ Imported ${data.candidate_ids.length} candidates`;
    toast(`CSV imported: ${data.candidate_ids.length} candidates`, 'success');
    await loadCandidates();
    setTimeout(() => switchView('dashboard'), 800);
  } catch (e) {
    resultEl.className = 'upload-result error';
    resultEl.textContent = `✗ ${e.message}`;
    toast(`CSV upload failed: ${e.message}`, 'error');
  } finally {
    setUploading('csv', false);
  }
}

async function handleResumeUpload() {
  const input  = document.getElementById('input-resume');
  const file   = input.files[0];
  if (!file) return;

  const enrichLLM = document.getElementById('resume-enrich').checked;
  const resultEl  = document.getElementById('resume-result');
  setUploading('resume', true);
  resultEl.className = 'upload-result';
  resultEl.textContent = '';

  const form = new FormData();
  form.append('file', file);
  form.append('enrich_with_llm', enrichLLM);

  try {
    const resp = await fetch(`${API_BASE}/candidates/from-resume`, { method: 'POST', body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Upload failed');
    resultEl.className = 'upload-result success';
    resultEl.textContent = `✓ Profile created: ${data.candidate?.full_name || data.candidate_id}`;
    toast(`Resume processed: ${data.candidate?.full_name || 'unknown'}`, 'success');
    await loadCandidates();
    setTimeout(() => switchView('dashboard'), 800);
  } catch (e) {
    resultEl.className = 'upload-result error';
    resultEl.textContent = `✗ ${e.message}`;
    toast(`Resume upload failed: ${e.message}`, 'error');
  } finally {
    setUploading('resume', false);
  }
}

// ─── Semantic Search ──────────────────────────────────────────
function setupSearch() {
  document.getElementById('btn-search').addEventListener('click', () => {
    const q = document.getElementById('search-input').value.trim();
    if (q) runSearch(q);
  });
  document.getElementById('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('btn-search').click();
  });
}

window.runSearch = async function(query) {
  document.getElementById('search-input').value = query;
  switchView('search');
  const resultsEl = document.getElementById('search-results');
  resultsEl.innerHTML = '<p style="color:var(--text-muted)">Searching…</p>';

  try {
    const resp = await fetch(`${API_BASE}/candidates/search?q=${encodeURIComponent(query)}&top_k=10`);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Search failed');

    if (!data.results || !data.results.length) {
      resultsEl.innerHTML = '<p style="color:var(--text-muted)">No results found.</p>';
      return;
    }

    resultsEl.innerHTML = data.results.map(r => {
      const c = r.candidate;
      const initials = (c.full_name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
      return `
        <div class="search-result-card" onclick="openDrawer(${JSON.stringify(c).replace(/"/g, '&quot;')})">
          <div class="card-avatar" style="width:36px;height:36px;font-size:13px">${initials}</div>
          <div class="search-result-body">
            <div class="search-result-name">${esc(c.full_name || 'Unknown')}</div>
            <div class="search-result-chunk">${esc(r.matched_chunk || '')}</div>
          </div>
          <div class="search-result-score">${(r.relevance_score * 100).toFixed(0)}%</div>
        </div>`;
    }).join('');
  } catch (e) {
    resultsEl.innerHTML = `<p style="color:var(--red)">Search failed: ${esc(e.message)}</p>`;
  }
};

// ─── Utils ─────────────────────────────────────────────────────
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function locationStr(loc) {
  if (!loc) return '—';
  return [loc.city, loc.region, loc.country].filter(Boolean).join(', ') || '—';
}

function infoRow(key, value) {
  return `<div class="info-row"><span class="info-key">${key}</span><span class="info-value">${value || '—'}</span></div>`;
}

function toast(message, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  toastCont.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
