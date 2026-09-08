const $ = (id) => document.getElementById(id);
let selectedFile = null;
let useSample = false;

function setInput(file, sample = false) {
  if (!sample && (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) return showError('Please choose a JPG, PNG, or WEBP image.');
  useSample = sample;
  selectedFile = file;
  $('selected-file').hidden = false;
  $('input-preview').src = sample ? '/artifacts/case-001/input.jpg' : URL.createObjectURL(file);
  $('input-name').textContent = sample ? 'case-001 / input.jpg' : file.name;
  $('input-meta').textContent = sample ? 'Existing preserved demo artifact' : `${file.type.split('/')[1].toUpperCase()} / ${(file.size / 1024).toFixed(1)} KB`;
  $('file-label').textContent = sample ? 'case-001 sample selected' : file.name;
  $('case-label').textContent = sample ? 'CASE-001 / SAMPLE' : 'CASE-002 / UPLOAD';
  $('analyze-button').disabled = false;
  $('error').hidden = true;
}

function showError(message) { $('error').textContent = message; $('error').hidden = false; }
function setProgress(step, label) { $('progress-panel').hidden = false; $('progress-label').textContent = label; $('progress-count').textContent = `${step} / 5`; $('progress-bar').style.width = `${step * 20}%`; document.querySelectorAll('[data-step]').forEach((node) => node.classList.toggle('active', Number(node.dataset.step) <= step)); }
function pause(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
async function fileAsBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return btoa(binary);
}

async function analyze() {
  $('analyze-button').disabled = true; $('results').hidden = true; $('error').hidden = true;
  try {
    setProgress(1, 'Detecting face'); await pause(250); setProgress(2, 'Searching Google Lens'); await pause(250); setProgress(3, 'Comparing candidates');
    const payload = { useSample, sourceUrl: $('source-url-input').value.trim() };
    if (!useSample) { payload.type = selectedFile.type; payload.data = await fileAsBase64(selectedFile); }
    const response = await fetch('/api/analyze', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
    setProgress(4, 'Anchoring selected artifact');
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'Analysis failed');
    setProgress(5, 'Verifying blockchain record'); await pause(300); renderResults(result);
  } catch (error) { showError(error.message); $('progress-panel').hidden = true; } finally { $('analyze-button').disabled = false; }
}

function renderResults(result) {
  const selected = result.candidate; const chain = result.anchoring;
  $('results').hidden = false; $('result-input').src = result.inputUrl; $('result-candidate').src = result.candidateUrl;
  $('candidate-rank').textContent = `#${selected.search_rank}`; $('similarity').textContent = selected.best_face_similarity.toFixed(4); $('threshold').textContent = selected.qualifies ? 'passed' : 'not met';
  $('source-url').textContent = result.sourceUrl; $('source-url').href = result.sourceUrl; $('source-link').href = result.sourceUrl;
  $('sha256').textContent = chain.artifact.sha256; $('tx-hash').textContent = chain.transaction_hash || 'Existing registration'; $('block-number').textContent = chain.block_number || 'Existing record'; $('chain-id').textContent = chain.chain_id || '31337';
  const verified = result.verified; $('status-pill').textContent = verified ? 'VERIFIED' : 'FAILED'; $('verification-title').textContent = verified ? 'VERIFIED' : 'FAILED'; $('verification-copy').textContent = verified ? 'The preserved artifact matches the fingerprint recorded on-chain.' : 'The artifact does not match the fingerprint recorded on-chain.'; $('final-status').classList.toggle('failed', !verified); $('connection-label').textContent = verified ? 'Pipeline complete' : 'Verification failed'; $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('image-input').addEventListener('change', (event) => setInput(event.target.files[0])); $('sample-button').addEventListener('click', () => setInput(null, true)); $('analyze-button').addEventListener('click', analyze);
['dragenter', 'dragover'].forEach((name) => $('dropzone').addEventListener(name, (event) => { event.preventDefault(); $('dropzone').classList.add('dragging'); })); ['dragleave', 'drop'].forEach((name) => $('dropzone').addEventListener(name, (event) => { event.preventDefault(); $('dropzone').classList.remove('dragging'); })); $('dropzone').addEventListener('drop', (event) => setInput(event.dataTransfer.files[0]));
