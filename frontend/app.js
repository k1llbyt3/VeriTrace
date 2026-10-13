/**
 * VeriTrace frontend — Evidence Console
 *
 * Handles image selection, case loading, analysis submission, clear workspace,
 * session-based state persistence, and result rendering.
 *
 * No live SerpApi/Lens calls are made here. All analysis is delegated to the
 * backend via /api/analyze. Existing cases are loaded via /api/case/:id.
 */

'use strict';

/* ── DOM helpers ─────────────────────────────────────────────────────── */
const $ = (id) => document.getElementById(id);

/* ── State ───────────────────────────────────────────────────────────── */
let selectedFile     = null;
let selectedBase64   = null;
let selectedFileType = null;
let selectedFileName = null;
let selectedFileSize = 0;
let useSample        = false;

/** Counter incremented on every new analysis; lets us discard stale responses. */
let requestSerial = 0;

/* ── sessionStorage helpers ──────────────────────────────────────────── */
function saveState(extra = {}) {
  try {
    const state = {
      useSample,
      selectedBase64,
      selectedFileType,
      selectedFileName,
      selectedFileSize,
      lastCaseId:    extra.caseId   ?? null,
      lastResult:    extra.result   ?? null,
      sourceUrlInput: $('source-url-input')?.value ?? '',
    };
    sessionStorage.setItem('veritrace_state', JSON.stringify(state));
  } catch {
    // Ignore storage errors (quota exceeded, private browsing)
  }
}

function clearState() {
  try { sessionStorage.removeItem('veritrace_state'); } catch { /* ignore */ }
}

/* ── Result rendering ────────────────────────────────────────────────── */
function renderResults(result) {
  const selected = result.candidate;
  const chain    = result.anchoring;

  // ── Images ───────────────────────────────────────────────────────────
  $('result-input').src     = result.inputUrl     || '';
  $('result-candidate').src = result.candidateUrl || '';

  $('candidate-rank').textContent  = `#${selected.search_rank || 1}`;
  $('candidate-title').textContent = selected.title || '(untitled match)';

  // ── Source attribution ────────────────────────────────────────────────
  const sourceUrl = result.sourceUrl || selected.source_url || '';
  const sourceEl  = $('source-url');
  const linkEl    = $('source-link');
  if (sourceUrl) {
    sourceEl.textContent = sourceUrl;
    sourceEl.href        = sourceUrl;
    sourceEl.hidden      = false;
    linkEl.href          = sourceUrl;
    linkEl.hidden        = false;
  } else {
    sourceEl.textContent = 'No public source URL recorded';
    sourceEl.removeAttribute('href');
    sourceEl.hidden = false;
    linkEl.hidden   = true;
  }
  $('source-badge').textContent = sourceUrl ? 'UNCONFIRMED SOURCE' : 'NO SOURCE';

  // ── Face similarity ───────────────────────────────────────────────────
  const simScore = typeof selected.best_face_similarity === 'number'
    ? selected.best_face_similarity
    : parseFloat(selected.best_face_similarity) || 0;
  $('similarity').textContent = simScore > 0 ? simScore.toFixed(4) : '—';
  $('score-bar').style.width  = `${Math.min(100, Math.max(0, simScore * 100)).toFixed(1)}%`;

  const passes = Boolean(selected.qualifies);
  $('threshold').textContent  = passes ? 'passed (≥ 0.40)' : 'below threshold (< 0.40)';
  $('face-badge').textContent = passes ? 'SIMILARITY PASS' : 'BELOW THRESHOLD';
  $('face-badge').className   = `layer-badge ${passes ? 'layer-badge--green' : 'layer-badge--red'}`;

  // ── SHA-256 integrity ─────────────────────────────────────────────────
  const sha256 = chain.artifact ? chain.artifact.sha256 : (chain.sha256 || '');
  $('sha256').textContent = sha256 || '—';
  $('hash-badge').textContent = sha256 ? 'FINGERPRINT READY' : 'NO HASH';
  $('hash-badge').className   = `layer-badge ${sha256 ? 'layer-badge--green' : ''}`;

  // ── Blockchain record ─────────────────────────────────────────────────
  $('tx-hash').textContent       = chain.transaction_hash || 'Existing registration';
  $('block-number').textContent  = chain.block_number != null ? chain.block_number : 'Existing record';
  $('chain-id').textContent      = chain.chain_id || '31337';
  $('contract-address').textContent = chain.contract_address || '—';

  const hasChainRecord = Boolean(chain.transaction_hash || chain.block_number);
  $('chain-badge').textContent = hasChainRecord ? 'ON-CHAIN' : 'LOCAL RECORD';
  $('chain-badge').className   = `layer-badge ${hasChainRecord ? 'layer-badge--green' : ''}`;

  // ── Overall verification verdict ──────────────────────────────────────
  const verified = Boolean(result.verified);
  const pill = $('status-pill');
  pill.textContent = verified ? 'VERIFIED' : 'UNVERIFIED';
  pill.className   = `status-pill${verified ? '' : ' failed'}`;

  const verdictEl = $('verdict');
  const markEl    = $('verdict-mark');
  $('verdict-title').textContent = verified
    ? 'BLOCKCHAIN VERIFICATION PASSED'
    : 'BLOCKCHAIN VERIFICATION FAILED';
  $('verdict-copy').textContent = verified
    ? 'The preserved artifact exactly matches the fingerprint recorded on-chain.'
    : 'The artifact hash does not match the fingerprint recorded on-chain, or the record is unavailable.';
  markEl.textContent = verified ? '✓' : '✗';
  verdictEl.className = `verdict${verified ? '' : ' failed'}`;

  // ── Show section ──────────────────────────────────────────────────────
  $('results-panel').hidden  = false;
  $('progress-panel').hidden = true;
  $('results-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ── Progress indicator ──────────────────────────────────────────────── */
function setProgress(step, label) {
  $('progress-panel').hidden = false;
  $('progress-label').textContent  = label;
  $('progress-count').textContent  = `${step} / 5`;
  $('progress-fill').style.width   = `${step * 20}%`;
  document.querySelectorAll('.progress-steps [data-step]').forEach((el) => {
    el.classList.toggle('active', Number(el.dataset.step) <= step);
  });
}

function pause(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ── Error display ───────────────────────────────────────────────────── */
function showError(msg) {
  const el = $('error-msg');
  el.textContent = msg;
  el.hidden = false;
}

/* ── File utilities ──────────────────────────────────────────────────── */
async function fileAsBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/* ── Set input image ─────────────────────────────────────────────────── */
async function setInput(file, sample = false, persist = true) {
  if (!sample && (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
    return showError('Please choose a JPG, PNG, or WEBP image.');
  }
  useSample = sample;
  selectedFile = file;

  // Reset previous results
  $('results-panel').hidden = true;
  $('error-msg').hidden     = true;
  $('clear-btn').hidden     = false;

  if (sample) {
    selectedBase64   = null;
    selectedFileType = null;
    selectedFileName = 'case-001 / input.jpg';
    selectedFileSize = 0;
    $('input-preview').src      = '/artifacts/case-001/input.jpg';
    $('input-name').textContent  = 'case-001 / input.jpg';
    $('input-meta').textContent  = 'Preserved demo artifact';
    $('file-label').textContent  = 'case-001 sample selected';
    $('case-badge').textContent  = 'CASE-001 / SAMPLE';
  } else {
    selectedFileType = file.type;
    selectedFileName = file.name;
    selectedFileSize = file.size;
    selectedBase64   = await fileAsBase64(file);
    $('input-preview').src      = `data:${selectedFileType};base64,${selectedBase64}`;
    $('input-name').textContent  = file.name;
    $('input-meta').textContent  = `${file.type.split('/')[1].toUpperCase()} · ${(file.size / 1024).toFixed(1)} KB`;
    $('file-label').textContent  = file.name;
    $('case-badge').textContent  = 'NEW UPLOAD';
  }

  $('selected-preview').hidden = false;
  $('analyze-btn').disabled    = false;

  if (persist) saveState({ result: null });
}

/* ── Clear workspace ─────────────────────────────────────────────────── */
function clearWorkspace() {
  requestSerial++; // invalidate any in-flight request
  selectedFile     = null;
  selectedBase64   = null;
  selectedFileType = null;
  selectedFileName = null;
  selectedFileSize = 0;
  useSample        = false;

  $('image-input').value          = '';
  $('source-url-input').value     = '';
  $('file-label').textContent     = 'Drop an image or click to browse';
  $('case-badge').textContent     = '';
  $('input-name').textContent     = '—';
  $('input-meta').textContent     = '—';
  $('input-preview').src          = '';
  $('selected-preview').hidden    = true;
  $('results-panel').hidden       = true;
  $('progress-panel').hidden      = true;
  $('error-msg').hidden           = true;
  $('analyze-btn').disabled       = true;
  $('clear-btn').hidden           = true;


  clearState();
}

/* ── Load an existing case ───────────────────────────────────────────── */
async function loadCase(caseId) {
  $('results-panel').hidden = true;
  $('error-msg').hidden     = true;
  $('clear-btn').hidden     = false;
  $('analyze-btn').disabled = false;
  setProgress(1, `Reading ${caseId} artifacts`);

  const serial = ++requestSerial;

  try {
    const response = await fetch(`/api/case/${encodeURIComponent(caseId)}`);
    const result   = await response.json();

    if (serial !== requestSerial) return; // superseded
    if (!response.ok || !result.ok) throw new Error(result.error || `Failed to load ${caseId}`);

    setProgress(5, 'Case record loaded');
    await pause(200);
    $('progress-panel').hidden = true;

    // Show the preserved input image
    $('input-preview').src      = result.inputUrl;
    $('input-name').textContent  = `${caseId} / input.jpg`;
    $('input-meta').textContent  = 'Preserved case artifact';
    $('file-label').textContent  = `${caseId} loaded`;
    $('case-badge').textContent  = `${caseId.toUpperCase()} / PRESERVED`;
    $('selected-preview').hidden = false;

    renderResults(result);
    saveState({ caseId, result });
  } catch (err) {
    if (serial !== requestSerial) return;
    $('progress-panel').hidden = true;
    showError(err.message);
  }
}

/* ── Restore session state ───────────────────────────────────────────── */
function restoreState() {
  try {
    const raw = sessionStorage.getItem('veritrace_state');
    if (!raw) return;
    const state = JSON.parse(raw);

    if (state.sourceUrlInput && $('source-url-input')) {
      $('source-url-input').value = state.sourceUrlInput;
    }

    // Restore input image preview
    if (state.useSample) {
      setInput(null, true, false);
    } else if (state.selectedBase64 && state.selectedFileName) {
      selectedBase64   = state.selectedBase64;
      selectedFileType = state.selectedFileType;
      selectedFileName = state.selectedFileName;
      selectedFileSize = state.selectedFileSize;
      useSample        = false;
      $('input-preview').src      = `data:${selectedFileType};base64,${selectedBase64}`;
      $('input-name').textContent  = selectedFileName;
      $('input-meta').textContent  = `${(selectedFileType || 'IMAGE').split('/')[1]?.toUpperCase() || 'IMG'} · ${(selectedFileSize / 1024).toFixed(1)} KB`;
      $('file-label').textContent  = selectedFileName;
      $('case-badge').textContent  = state.lastCaseId ? `${state.lastCaseId.toUpperCase()} / UPLOAD` : 'UPLOADED IMAGE';
      $('selected-preview').hidden = false;
      $('analyze-btn').disabled    = false;
      $('clear-btn').hidden        = false;
    } else if (state.lastCaseId && !state.selectedBase64) {
      // Preserved case — show preview placeholder via the preserved input URL
      $('input-preview').src      = `/artifacts/${state.lastCaseId}/input.jpg`;
      $('input-name').textContent  = `${state.lastCaseId} / input.jpg`;
      $('input-meta').textContent  = 'Preserved case artifact';
      $('file-label').textContent  = `${state.lastCaseId} loaded`;
      $('case-badge').textContent  = `${state.lastCaseId.toUpperCase()} / PRESERVED`;
      $('selected-preview').hidden = false;
      $('analyze-btn').disabled    = false;
      $('clear-btn').hidden        = false;
    }

    // Restore results — prefer cached result object; fall back to loading from backend
    if (state.lastResult) {
      renderResults(state.lastResult);
    } else if (state.lastCaseId) {
      // Only reload if we actually have a case record (not a new upload in progress)
      if (!state.selectedBase64) {
        loadCase(state.lastCaseId);
      }
    }
  } catch {
    // Ignore deserialization errors
  }
}

/* ── Analyze ─────────────────────────────────────────────────────────── */
async function analyze() {
  $('analyze-btn').disabled = true;
  $('results-panel').hidden = true;
  $('error-msg').hidden     = true;

  const serial = ++requestSerial;

  try {
    setProgress(1, 'Detecting face');
    await pause(180);
    setProgress(2, 'Checking preserved artifacts & search cache');
    await pause(180);
    setProgress(3, 'Comparing candidates');

    const payload = {
      useSample,
      sourceUrl: $('source-url-input').value.trim(),
    };

    if (!useSample) {
      if (!selectedBase64 && selectedFile) {
        selectedBase64 = await fileAsBase64(selectedFile);
      }
      payload.type = selectedFileType || selectedFile?.type;
      payload.data = selectedBase64;
    }

    const response = await fetch('/api/analyze', {
      method:  'POST',
      headers: { 'content-type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    if (serial !== requestSerial) return;

    setProgress(4, 'Anchoring selected artifact');
    const result = await response.json();

    if (!response.ok || !result.ok) {
      throw new Error(result.error || `Analysis failed (stage: ${result.stage || 'unknown'})`);
    }

    setProgress(5, 'Verifying blockchain record');
    await pause(220);

    if (serial !== requestSerial) return;

    renderResults(result);
    saveState({ caseId: result.caseId, result });
  } catch (err) {
    if (serial !== requestSerial) return;
    showError(err.message);
    $('progress-panel').hidden = true;
  } finally {
    if (serial === requestSerial) {
      $('analyze-btn').disabled = false;
    }
  }
}

/* ── Event listeners ─────────────────────────────────────────────────── */
$('image-input').addEventListener('change', (e) => setInput(e.target.files[0]));
$('analyze-btn').addEventListener('click', analyze);
$('clear-btn').addEventListener('click', clearWorkspace);

$('load-case001-btn')?.addEventListener('click', () => loadCase('case-001'));
$('load-case002-btn')?.addEventListener('click', () => loadCase('case-002'));

// Drag and drop
['dragenter', 'dragover'].forEach((name) =>
  $('dropzone').addEventListener(name, (e) => {
    e.preventDefault();
    $('dropzone').classList.add('dragging');
  }),
);
['dragleave', 'drop'].forEach((name) =>
  $('dropzone').addEventListener(name, (e) => {
    e.preventDefault();
    $('dropzone').classList.remove('dragging');
  }),
);
$('dropzone').addEventListener('drop', (e) => setInput(e.dataTransfer.files[0]));

/* ── Init ────────────────────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', restoreState);