// ─────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────
const API_BASE = "http://localhost:5000/api";
let currentAnalysisId = null; // tracks the most recently uploaded/analyzed file

// ─────────────────────────────────────────────────────────
// Sidebar toggle (mobile)
// ─────────────────────────────────────────────────────────
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('overlay');
const hamburger = document.getElementById('hamburger');
hamburger.addEventListener('click', () => {
  sidebar.classList.toggle('open');
  overlay.classList.toggle('show');
});
overlay.addEventListener('click', () => {
  sidebar.classList.remove('open');
  overlay.classList.remove('show');
});

// nav active state
function setActive(el) {
  event.preventDefault();
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  if (window.innerWidth <= 768) {
    sidebar.classList.remove('open');
    overlay.classList.remove('show');
  }
}

// ─────────────────────────────────────────────────────────
// Toast notifications
// ─────────────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const colors = {
    success: { bg: 'rgba(0,230,118,.15)', border: 'rgba(0,230,118,.4)', text: '#00e676' },
    error: { bg: 'rgba(255,77,109,.15)', border: 'rgba(255,77,109,.4)', text: '#ff4d6d' },
    info: { bg: 'rgba(0,168,255,.15)', border: 'rgba(0,168,255,.4)', text: '#00a8ff' },
  };
  const c = colors[type] || colors.info;
  const t = document.createElement('div');
  t.textContent = message;
  Object.assign(t.style, {
    position: 'fixed', bottom: '24px', right: '24px',
    background: c.bg, border: `1px solid ${c.border}`,
    color: c.text, borderRadius: '10px', padding: '12px 20px',
    fontSize: '13px', fontWeight: '600', zIndex: '9999',
    boxShadow: '0 4px 20px rgba(0,0,0,.4)', maxWidth: '320px',
  });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ─────────────────────────────────────────────────────────
// File upload — wired to POST /api/upload
// ─────────────────────────────────────────────────────────
function triggerUpload() {
  document.getElementById('fileInput').click();
}

function handleFile(e) {
  const f = e.target.files[0];
  if (f) uploadAndAnalyze(f);
}

function handleDrop(e) {
  e.preventDefault();
  const f = e.dataTransfer.files[0];
  if (f) uploadAndAnalyze(f);
}

async function uploadAndAnalyze(file) {
  // client-side checks matching backend limits
  const allowed = ['.v', '.sv'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!allowed.includes(ext)) {
    showToast('Unsupported file type. Use .v or .sv files.', 'error');
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    showToast('File exceeds 5MB limit.', 'error');
    return;
  }

  showToast(`Uploading "${file.name}"…`, 'info');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.error || 'Upload failed.', 'error');
      return;
    }

    const result = await res.json();
    currentAnalysisId = result.id;

    showToast(`"${file.name}" analyzed — score ${result.analysis.score}/100`, 'success');

    renderAnalysisResults(result);
    renderOptimizations(result.optimizations);
    refreshStats();
    refreshHistory();

  } catch (err) {
    console.error(err);
    showToast('Could not reach the backend server. Is it running on localhost:5000?', 'error');
  }
}

// ─────────────────────────────────────────────────────────
// Render analysis results into the "Analysis Results" preview card
// ─────────────────────────────────────────────────────────
function renderAnalysisResults(result) {
  const { analysis } = result;
  const card = document.querySelectorAll('.preview-card')[1]; // Analysis Results card
  if (!card) return;

  const scoreNum = card.querySelector('.score-num');
  if (scoreNum) scoreNum.textContent = analysis.score;

  const dots = card.querySelectorAll('.score-dot .num');
  if (dots.length === 3) {
    dots[0].textContent = analysis.counts.errors;
    dots[1].textContent = analysis.counts.warnings;
    dots[2].textContent = analysis.counts.infos;
  }

  // update the score ring stroke-dashoffset proportionally
  const ring = card.querySelector('.score-ring circle:nth-of-type(2)');
  if (ring) {
    const circumference = 163; // matches existing markup's dasharray
    const offset = circumference * (1 - analysis.score / 100);
    ring.setAttribute('stroke-dashoffset', offset.toFixed(0));
  }

  // replace issues list (cap to 3 shown, matching the dashboard preview style)
  const issuesContainer = card.querySelectorAll('.issue-item');
  issuesContainer.forEach(el => el.remove());

  const issuesParent = card.querySelector('.preview-body');
  const topIssues = analysis.issues.slice(0, 3);

  topIssues.forEach(issue => {
    const div = document.createElement('div');
    div.className = 'issue-item';
    const dotClass = issue.severity === 'error' ? 'err' : issue.severity === 'warning' ? 'warn' : 'info';
    const labelColor = issue.severity === 'error' ? 'var(--red)' : issue.severity === 'warning' ? 'var(--yellow)' : 'var(--blue-bright)';
    div.innerHTML = `
      <div class="dot ${dotClass}"></div>
      <div>
        <div class="issue-title" style="color:${labelColor}">${capitalize(issue.severity)}</div>
        <div class="issue-desc">Line ${issue.line}: ${issue.message}</div>
      </div>`;
    issuesParent.appendChild(div);
  });
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ─────────────────────────────────────────────────────────
// Render optimization suggestions into the "Optimizations" preview card
// ─────────────────────────────────────────────────────────
function renderOptimizations(optimizations) {
  const card = document.querySelectorAll('.preview-card')[2]; // Optimizations card
  if (!card) return;

  const existing = card.querySelectorAll('.opt-item');
  existing.forEach(el => el.remove());

  const parent = card.querySelector('.preview-body');
  optimizations.slice(0, 3).forEach(opt => {
    const div = document.createElement('div');
    div.className = 'opt-item';
    div.innerHTML = `
      <div class="opt-header">
        <div class="opt-title">${opt.title}</div>
        <div class="badge ${opt.impact}">${capitalize(opt.impact)} Impact</div>
      </div>
      <div class="opt-desc">${opt.description}</div>`;
    parent.appendChild(div);
  });
}

// ─────────────────────────────────────────────────────────
// Dashboard stats — wired to GET /api/stats
// ─────────────────────────────────────────────────────────
async function refreshStats() {
  try {
    const res = await fetch(`${API_BASE}/stats`);
    if (!res.ok) return;
    const stats = await res.json();

    const statCards = document.querySelectorAll('.stat-card');
    if (statCards.length === 5) {
      statCards[0].querySelector('.stat-value').textContent = stats.total_analyses;
      statCards[1].querySelector('.stat-value').textContent = stats.errors_found;
      statCards[2].querySelector('.stat-value').textContent = stats.warnings;
      statCards[3].querySelector('.stat-value').textContent = stats.optimizations;
      statCards[4].querySelector('.stat-value').textContent = stats.success_rate + '%';
    }
  } catch (err) {
    console.warn('Could not refresh stats:', err);
  }
}

// ─────────────────────────────────────────────────────────
// Recent files — wired to GET /api/history
// ─────────────────────────────────────────────────────────
async function refreshHistory() {
  try {
    const res = await fetch(`${API_BASE}/history?limit=5`);
    if (!res.ok) return;
    const items = await res.json();

    const uploadCard = document.querySelectorAll('.preview-card')[0];
    if (!uploadCard) return;

    const existingRows = uploadCard.querySelectorAll('.recent-file');
    existingRows.forEach(el => el.remove());

    const parent = uploadCard.querySelector('.preview-body');
    items.forEach(item => {
      const div = document.createElement('div');
      div.className = 'recent-file';
      const when = timeAgo(item.uploaded_at);
      div.innerHTML = `
        <div class="recent-file-name"><span class="file-icon">📄</span>${item.filename}</div>
        <div class="recent-file-meta">${item.size_kb} KB &nbsp; ${when}</div>`;
      parent.appendChild(div);
    });
  } catch (err) {
    console.warn('Could not refresh history:', err);
  }
}

function timeAgo(isoString) {
  const then = new Date(isoString);
  const diffMs = Date.now() - then.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ─────────────────────────────────────────────────────────
// PDF report generation — wired to POST /api/report/<id>
// ─────────────────────────────────────────────────────────
document.querySelector('.btn-generate').addEventListener('click', async () => {
  const btn = document.querySelector('.btn-generate');

  if (!currentAnalysisId) {
    showToast('Upload and analyze a file first.', 'error');
    return;
  }

  btn.textContent = 'Generating…';
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/report/${currentAnalysisId}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.error || 'Report generation failed.', 'error');
      return;
    }
    const data = await res.json();
    showToast('Report generated successfully', 'success');

    // trigger browser download
    window.open(`${API_BASE}/report/${currentAnalysisId}/download`, '_blank');

  } catch (err) {
    console.error(err);
    showToast('Could not reach the backend server.', 'error');
  } finally {
    btn.textContent = 'Generate PDF Report';
    btn.disabled = false;
  }
});

// "Download Last Report" link
document.querySelector('.download-link').addEventListener('click', (e) => {
  e.preventDefault();
  window.open(`${API_BASE}/report/last`, '_blank');
});

// ─────────────────────────────────────────────────────────
// Initial load — populate dashboard with real backend data
// ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  refreshStats();
  refreshHistory();
});
