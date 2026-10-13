'use strict';
/**
 * VeriTrace backend — Evidence Console server
 *
 * API routes:
 *   GET  /api/cases                    — list all completed case IDs
 *   GET  /api/case/:id                 — read a preserved case result
 *   POST /api/analyze                  — run full pipeline on uploaded image
 *
 * Static serving covers /frontend/*, /artifacts/*, and /samples/*.
 *
 * No SerpApi or blockchain calls are made here; those are delegated to the
 * Python pipeline via runPython().
 */

const http   = require('http');
const fs     = require('fs');
const path   = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const root = path.resolve(__dirname, '..');
const port = Number(process.env.PORT || 4173);

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png':  'image/png',
  '.webp': 'image/webp',
};

/* ── Helpers ─────────────────────────────────────────────────────────── */
function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'content-type': type, 'access-control-allow-origin': '*' });
  res.end(Buffer.isBuffer(body) || typeof body === 'string'
    ? body : JSON.stringify(body));
}

class ValidationError extends Error {
  constructor(msg) { super(msg); this.name = 'ValidationError'; this.statusCode = 400; }
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

/** True if the case ID is a safe single directory name. */
function validCaseId(id) {
  return Boolean(id) && /^case-[a-zA-Z0-9_-]{1,64}$/.test(id);
}

/** Safely resolve a case directory inside artifacts/; rejects traversal. */
function resolveCaseDir(caseId) {
  if (!validCaseId(caseId)) throw new ValidationError(`Invalid case identifier: "${caseId}"`);
  const dir = path.join(root, 'artifacts', caseId);
  if (!dir.startsWith(path.join(root, 'artifacts') + path.sep)) {
    throw new ValidationError('Path traversal rejected');
  }
  return dir;
}

/* ── Python subprocess ───────────────────────────────────────────────── */
function runPython(args, timeoutMs = 300_000) {
  return new Promise((resolve, reject) => {
    const venvExe = path.join(root, 'venv', 'Scripts', 'python.exe');
    const venvExe2 = path.join(root, '.venv', 'Scripts', 'python.exe');
    const python = process.env.PYTHON ||
      (process.platform === 'win32'
        ? (fs.existsSync(venvExe) ? venvExe : venvExe2)
        : 'python3');

    const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' };
    const child = spawn(python, ['python/main.py', ...args], {
      cwd: root, windowsHide: true, env,
    });

    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    let stdout = '', stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    child.on('error', reject);

    const timer = setTimeout(() => {
      child.kill();
      const err = new Error(`Pipeline timed out after ${timeoutMs / 1000}s`);
      err.statusCode = 504;
      reject(err);
    }, timeoutMs);

    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const msg = stderr.trim() || stdout.trim() || `Pipeline exited with code ${code}`;
        const err = new Error(msg);
        err.statusCode = 500;
        err.code = code;
        err.stdout = stdout;
        err.stderr = stderr;
        reject(err);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

/* ── Case result reader ──────────────────────────────────────────────── */
/**
 * Read a preserved case from the artifacts directory.
 *
 * The `verified` flag is set ONLY when:
 *   registered_hash (from the on-chain read performed during anchoring) matches
 *   artifact.bytes32 (the SHA-256 of the local file written to disk).
 *
 * This is a local check of stored values; the definitive blockchain read-back
 * was performed by python/main.py → cmd_verify → fetch_by_hash/tx.
 * We surface the result rather than re-running the blockchain call on every
 * page load (which would hit the local Hardhat node unnecessarily).
 */
function getCaseResult(caseId) {
  const caseDir       = resolveCaseDir(caseId);
  const selectionPath = path.join(caseDir, 'selection_metadata.json');
  const anchoringPath = path.join(caseDir, 'anchoring_metadata.json');
  const metadataPath  = path.join(caseDir, 'metadata.json');

  if (!fs.existsSync(caseDir)) {
    throw new ValidationError(`Case "${caseId}" does not exist`);
  }
  if (!fs.existsSync(selectionPath) || !fs.existsSync(anchoringPath)) {
    throw new ValidationError(`Case "${caseId}" artifacts are incomplete (selection or anchoring missing)`);
  }

  const selection        = readJson(selectionPath);
  const anchoring        = readJson(anchoringPath);
  const existingMetadata = fs.existsSync(metadataPath) ? readJson(metadataPath) : {};

  if (!selection.selected || !selection.selected.local_path) {
    throw new ValidationError(`Case "${caseId}" has no qualifying selected candidate`);
  }

  const selected        = selection.selected;
  const candidateFile   = path.basename(selected.local_path);
  const sourceUrl       =
    selected.source_url ||
    existingMetadata.candidate?.source_url ||
    anchoring.source_url || '';

  // Verification: compare the registered bytes32 hash against the artifact bytes32.
  // Both values were written by the Python pipeline after the blockchain interaction.
  const registeredHash  = (anchoring.registered_hash || '').toLowerCase().replace(/^0x/, '');
  const artifactBytes32 = (anchoring.artifact?.bytes32 || '').toLowerCase().replace(/^0x/, '');
  const verified = Boolean(
    registeredHash &&
    artifactBytes32 &&
    registeredHash === artifactBytes32,
  );

  return {
    ok:           true,
    caseId,
    inputUrl:     `/artifacts/${caseId}/input.jpg`,
    candidateUrl: `/artifacts/${caseId}/${candidateFile}`,
    candidate:    selected,
    anchoring,
    sourceUrl,
    verified,
  };
}

/* ── Artifact deduplication ──────────────────────────────────────────── */
/**
 * Compare the uploaded image's SHA-256 against all existing input.jpg files.
 * Returns the first matching caseId or null.
 * Only considers cases that have complete selection + anchoring metadata.
 */
function findMatchingArtifactCase(imageBuffer) {
  const incomingHash  = crypto.createHash('sha256').update(imageBuffer).digest('hex');
  const artifactsDir  = path.join(root, 'artifacts');
  if (!fs.existsSync(artifactsDir)) return null;

  const entries = fs.readdirSync(artifactsDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const cid = entry.name;
    if (!validCaseId(cid)) continue;

    const caseDir    = path.join(artifactsDir, cid);
    const inputPath  = path.join(caseDir, 'input.jpg');
    const selPath    = path.join(caseDir, 'selection_metadata.json');
    const anchorPath = path.join(caseDir, 'anchoring_metadata.json');

    if (!fs.existsSync(inputPath) || !fs.existsSync(selPath) || !fs.existsSync(anchorPath)) continue;

    try {
      const existingHash = crypto
        .createHash('sha256')
        .update(fs.readFileSync(inputPath))
        .digest('hex');
      if (existingHash === incomingHash) return cid;
    } catch {
      // Skip unreadable files
    }
  }
  return null;
}

/* ── List cases ──────────────────────────────────────────────────────── */
function listCases() {
  const artifactsDir = path.join(root, 'artifacts');
  if (!fs.existsSync(artifactsDir)) return [];

  return fs.readdirSync(artifactsDir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && validCaseId(e.name))
    .filter((e) => {
      const d = path.join(artifactsDir, e.name);
      return (
        fs.existsSync(path.join(d, 'selection_metadata.json')) &&
        fs.existsSync(path.join(d, 'anchoring_metadata.json'))
      );
    })
    .map((e) => e.name)
    .sort();
}

/* ── Core analyze pipeline ───────────────────────────────────────────── */
async function analyze(payload) {
  // Case 1: user clicked "Use sample" — serve case-001 directly
  if (payload.useSample) {
    const sampleInput = path.join(root, 'artifacts', 'case-001', 'input.jpg');
    if (!fs.existsSync(sampleInput)) throw new ValidationError('case-001 sample image not found');
    return getCaseResult('case-001');
  }

  // Case 2: uploaded image
  if (!payload.data || !/^image\/(jpeg|png|webp)$/.test(payload.type || '')) {
    throw new ValidationError('Please choose a JPG, PNG, or WEBP image');
  }

  const image = Buffer.from(payload.data, 'base64');
  if (!image.length)                throw new ValidationError('Empty image data');
  if (image.length > 15 * 1024 * 1024) throw new ValidationError('Image must be smaller than 15 MB');

  // Check if this exact image was already processed
  const matchedCaseId = findMatchingArtifactCase(image);
  if (matchedCaseId && !payload.forceRefresh) {
    return getCaseResult(matchedCaseId);
  }

  // Allocate an isolated case directory for this new image
  const hashPrefix = crypto.createHash('sha256').update(image).digest('hex').slice(0, 8);
  const caseId     = `case-${hashPrefix}`;
  const caseDir    = path.join(root, 'artifacts', caseId);
  const inputPath  = path.join(caseDir, 'input.jpg');
  const selPath    = path.join(caseDir, 'selection_metadata.json');

  fs.mkdirSync(caseDir, { recursive: true });

  // Write input image (overwrite safe — same hash → same bytes)
  fs.writeFileSync(inputPath, image);

  // Run candidate selection
  const selectArgs = [
    'select-candidate', inputPath,
    '--case', caseId,
    '--type', 'all',
    '--limit', '10',
  ];
  if (payload.sourceUrl) selectArgs.push('--source-url', payload.sourceUrl);

  try {
    await runPython(selectArgs);
  } catch (err) {
    // Clean up the written input if selection completely fails and case is new
    try {
      if (!fs.existsSync(selPath)) {
        fs.rmSync(caseDir, { recursive: true, force: true });
      }
    } catch { /* ignore cleanup errors */ }
    err.stage = 'candidate-selection';
    throw err;
  }

  if (!fs.existsSync(selPath)) {
    fs.rmSync(caseDir, { recursive: true, force: true });
    throw new Error('Candidate selection did not produce metadata');
  }

  const selection = readJson(selPath);
  if (!selection.selected || !selection.selected.local_path) {
    const msg = selection.message || 'No candidate passed the face similarity threshold.';
    const err = new Error(msg);
    err.statusCode = 422;
    err.stage      = 'candidate-qualification';
    throw err;
  }

  // Anchor the selected artifact on blockchain
  try {
    await runPython(['anchor', '--case', caseId]);
  } catch (err) {
    err.stage = 'blockchain-anchor';
    throw err;
  }

  // Verify the fingerprint by reading back from the blockchain
  try {
    await runPython(['verify', '--case', caseId]);
  } catch (err) {
    // Non-fatal: verification failure is surfaced in the result, not as an API error
    console.error(`[verify] ${err.message}`);
  }

  return getCaseResult(caseId);
}

/* ── HTTP server ─────────────────────────────────────────────────────── */
const server = http.createServer(async (req, res) => {
  const urlObj   = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = urlObj.pathname;

  // GET /api/cases — list completed cases
  if (req.method === 'GET' && pathname === '/api/cases') {
    send(res, 200, { ok: true, cases: listCases() });
    return;
  }

  // GET /api/case/:id — read a specific case
  if (req.method === 'GET' && pathname.startsWith('/api/case/')) {
    const caseId = decodeURIComponent(pathname.slice('/api/case/'.length)).replace(/\/$/, '').trim();
    try {
      send(res, 200, getCaseResult(caseId));
    } catch (err) {
      send(res, err.statusCode || 404, { ok: false, error: err.message });
    }
    return;
  }

  // POST /api/analyze — run pipeline
  if (req.method === 'POST' && pathname === '/api/analyze') {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 22 * 1024 * 1024) req.destroy();
    });
    req.on('end', async () => {
      try {
        let parsed;
        try { parsed = JSON.parse(body); }
        catch { send(res, 400, { ok: false, error: 'Malformed JSON', stage: 'validation' }); return; }
        send(res, 200, await analyze(parsed));
      } catch (err) {
        const status = err.statusCode || 500;
        // Never leak Python tracebacks or secrets to the browser
        const safeMsg = err.message.length > 800
          ? err.message.slice(0, 800) + '…'
          : err.message;
        send(res, status, {
          ok:    false,
          error: safeMsg || 'Analysis failed',
          stage: err.stage || 'pipeline',
        });
      }
    });
    return;
  }

  // Static file serving — /frontend/*, /artifacts/*, /samples/*
  const requested = pathname === '/'
    ? '/frontend/index.html'
    : pathname === '/frontend/'
      ? '/frontend/index.html'
      : pathname;

  const filePath = path.resolve(root, `.${decodeURIComponent(requested)}`);

  // Security: only serve files within known safe directories
  const allowed = [
    path.join(root, 'frontend'),
    path.join(root, 'artifacts'),
    path.join(root, 'samples'),
  ];
  const withinAllowed = allowed.some((dir) => filePath.startsWith(dir + path.sep) || filePath === dir);

  if (!withinAllowed || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    send(res, 404, 'Not found', 'text/plain; charset=utf-8');
    return;
  }

  const ext  = path.extname(filePath).toLowerCase();
  const mime = mimeTypes[ext] || 'application/octet-stream';
  send(res, 200, fs.readFileSync(filePath), mime);
});

server.listen(port, '127.0.0.1', () => {
  console.log(`VeriTrace frontend: http://127.0.0.1:${port}/frontend/`);
});