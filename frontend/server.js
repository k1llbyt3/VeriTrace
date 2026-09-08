const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const root = path.resolve(__dirname, '..');
const port = Number(process.env.PORT || 4173);
const mimeTypes = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8' };

function send(response, status, body, type = 'application/json; charset=utf-8') {
  response.writeHead(status, { 'content-type': type, 'access-control-allow-origin': '*' });
  response.end(Buffer.isBuffer(body) || typeof body === 'string' ? body : JSON.stringify(body));
}

function runPython(args) {
  return new Promise((resolve, reject) => {
    const python = process.env.PYTHON || (process.platform === 'win32' ? path.join(root, '.venv', 'Scripts', 'python.exe') : 'python3');
    const child = spawn(python, ['python/main.py', ...args], { cwd: root, windowsHide: true });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) { reject(new Error(stderr.trim() || stdout.trim() || 'Pipeline command failed')); return; }
      resolve({ stdout, stderr });
    });
  });
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

async function analyze(payload) {
  const caseId = payload.useSample ? 'case-001' : 'case-002';
  const caseDir = path.join(root, 'artifacts', caseId);
  const inputPath = path.join(caseDir, 'input.jpg');
  const metadataPath = path.join(caseDir, 'metadata.json');
  const existingMetadata = fs.existsSync(metadataPath) ? readJson(metadataPath) : {};
  if (payload.useSample) {
    if (!fs.existsSync(inputPath)) throw new Error('case-001 sample image is missing');
  } else {
    if (!payload.data || !/^image\/(jpeg|png|webp)$/.test(payload.type || '')) throw new Error('Please choose a JPG, PNG, or WEBP image');
    const image = Buffer.from(payload.data, 'base64');
    if (!image.length || image.length > 15 * 1024 * 1024) throw new Error('Image must be smaller than 15 MB');
    fs.mkdirSync(caseDir, { recursive: true });
    fs.writeFileSync(inputPath, image);
  }

  // The existing selection pipeline owns face detection, search, ranking, and preservation.
  let selection;
  try {
    const pipelineArgs = ['select-candidate', inputPath, '--case', caseId, '--type', 'all', '--limit', '10'];
    if (payload.sourceUrl) pipelineArgs.push('--source-url', payload.sourceUrl);
    await runPython(pipelineArgs);
    selection = readJson(path.join(caseDir, 'selection_metadata.json'));
  } catch (error) {
    if (!payload.useSample || !error.message.includes('Google Lens') || !fs.existsSync(path.join(caseDir, 'selection_metadata.json'))) throw error;
    selection = readJson(path.join(caseDir, 'selection_metadata.json'));
  }
  if (!selection.selected || !selection.selected.local_path) throw new Error('No qualifying candidate was found');
  await runPython(['anchor', '--case', caseId]);
  await runPython(['verify', '--case', caseId]);

  const anchoring = readJson(path.join(caseDir, 'anchoring_metadata.json'));
  const selected = selection.selected;
  return {
    ok: true,
    caseId,
    inputUrl: `/artifacts/${caseId}/input.jpg`,
    candidateUrl: `/artifacts/${caseId}/${path.basename(selected.local_path)}`,
    candidate: selected,
    anchoring,
    sourceUrl: selected.source_url || existingMetadata.candidate?.source_url || payload.sourceUrl || '',
    verified: anchoring.registered_hash.toLowerCase() === anchoring.artifact.bytes32.toLowerCase(),
  };
}

const server = http.createServer(async (request, response) => {
  if (request.method === 'POST' && request.url === '/api/analyze') {
    let body = '';
    request.on('data', (chunk) => { body += chunk; if (body.length > 22 * 1024 * 1024) request.destroy(); });
    request.on('end', async () => {
      try { send(response, 200, await analyze(JSON.parse(body))); }
      catch (error) { send(response, 400, { ok: false, error: error.message }); }
    });
    return;
  }

  const requested = request.url === '/' ? '/frontend/index.html' : request.url === '/frontend/' ? '/frontend/index.html' : request.url;
  const filePath = path.resolve(root, `.${decodeURIComponent(requested.split('?')[0])}`);
  if (!filePath.startsWith(root) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) { send(response, 404, 'Not found', 'text/plain; charset=utf-8'); return; }
  send(response, 200, fs.readFileSync(filePath), mimeTypes[path.extname(filePath)] || 'application/octet-stream');
});

server.listen(port, '127.0.0.1', () => console.log(`Goaa frontend: http://127.0.0.1:${port}/frontend/`));
