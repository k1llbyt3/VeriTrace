# VeriTrace: Face Identification and Blockchain Verification

VeriTrace is an end-to-end evidence verification pipeline that combines AI-based face similarity, reverse image search via Google Lens (SerpApi), SHA-256 cryptographic fingerprinting, and smart-contract anchoring on an EVM-compatible blockchain.

Given a reference face photograph, the system discovers real online content containing a matching face, selects the strongest candidate, fingerprints the preserved artifact, records that fingerprint on-chain, and later verifies whether the exact artifact is still intact.

---

## System Architecture

```text
INPUT IMAGE
    │
    ▼ SCRFD Face Detection
    │
    ▼ ArcFace Embedding
    │
    ▼ Google Lens via SerpApi (cache-first, no live call on reload)
    │
    ▼ Candidate Download & Validation
    │
    ▼ Face Comparison (cosine similarity per candidate)
    │
    ▼ Threshold Filter → Best Match Selection
    │
    ▼ Artifact Preserved (exact bytes)
    │
    ▼ SHA-256 Fingerprint
    │
    ▼ ContentRegistry on EVM Blockchain
    │
    ▼ Verification Read-back (recompute hash, compare on-chain)
    │
    VERIFIED / FAILED
```

### Three Distinct Evidence Layers

| Layer | What it proves |
|---|---|
| **ArcFace similarity** | Visual face embedding resemblance (not legal identity) |
| **SHA-256** | Exact byte-for-byte file integrity since registration |
| **Blockchain** | A fingerprint was recorded at this transaction; not ownership or authorship |

---

## Project Structure

```text
VeriTrace/
├── .env                          Environment secrets (not committed)
├── .env.example                  Template for environment configuration
├── requirements.txt              Python dependencies
├── specs/
│   └── HH_Goa_2026_Task3_PRD_TRD.md  Product + technical requirements
├── frontend/
│   ├── index.html                Evidence console UI
│   ├── styles.css                Clean technical styling
│   ├── app.js                    Frontend logic (state, rendering, clear workspace)
│   ├── server.js                 Node.js orchestration server + API routes
│   └── registration.json         (Hardhat deployment reference)
├── python/
│   ├── main.py                   Unified CLI entry point
│   ├── pipeline.py               End-to-end candidate selection orchestrator
│   ├── config.py                 Central .env-backed configuration
│   ├── chain/registry.py         Python → blockchain bridge (shells out to JS)
│   ├── evidence/hashing.py       SHA-256 fingerprinting
│   ├── face/detector.py          SCRFD face detector
│   ├── face/embedding.py         ArcFace embedding generation
│   ├── face/engine.py            Combined detector + embedder
│   ├── face/similarity.py        Cosine similarity utilities
│   ├── search/lens.py            SerpApi Google Lens client + caching + security
│   ├── search/cache.py           Local response cache
│   ├── search/downloader.py      Candidate image downloader
│   └── search/security.py        SSRF protection and URL validation
├── blockchain/
│   ├── contracts/ContentRegistry.sol  Solidity fingerprint registry
│   ├── scripts/chain.js          Shared ethers.js utilities
│   ├── scripts/register.js       Register a fingerprint on-chain
│   ├── scripts/fetch.js          Read back a fingerprint from the chain
│   ├── scripts/deploy.js         Deploy ContentRegistry
│   ├── deployments/localhost.json  Deployment receipt
│   └── test/ContentRegistry.test.js  Hardhat contract test suite
├── artifacts/                    Preserved case evidence (never auto-deleted)
│   └── case-<id>/
│       ├── input.jpg             Original uploaded image
│       ├── candidate-NNN.jpg     Downloaded candidate images
│       ├── metadata.json         Input source information
│       ├── selection_metadata.json  Candidate ranking and selection record
│       └── anchoring_metadata.json  SHA-256 + blockchain receipt
├── tests/                        Python unit + regression tests
│   ├── test_candidate_selection.py
│   ├── test_hashing.py
│   ├── test_lens_source_resolution.py
│   ├── test_search_pipeline.py
│   ├── test_similarity.py
│   ├── test_system_regression.py  Regression: path traversal, verified flag, dedup
│   └── test_unicode_output.py
├── samples/                      Demo reference images
└── tools/                        Developer utilities (live test, calibration)
```

---

## Prerequisites

### Python (3.10+)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Key packages: `insightface`, `onnxruntime`, `opencv-python-headless`, `pillow`, `numpy`, `requests`, `python-dotenv`.

### Node.js (18+)

```bash
cd blockchain
npm install
cd ..
```

---

## Configuration

Copy `.env.example` → `.env` and fill in your values:

```env
# Search
SERPAPI_KEY=your_serpapi_key_here

# Face pipeline
INSIGHTFACE_MODEL=buffalo_l
FACE_SIMILARITY_THRESHOLD=0.40

# Blockchain (local Hardhat defaults)
RPC_URL=http://127.0.0.1:8545
PRIVATE_KEY=                        # leave blank for local Hardhat test accounts
CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3
CHAIN_ID=31337
```

> **Security:** Never commit `.env`. The `.gitignore` excludes it.

---

## Running the Application

### 1. Start the local blockchain node

```bash
cd blockchain
npx hardhat node
```

Leave this running in its own terminal.

### 2. Deploy the contract (first time only)

```bash
cd blockchain
npx hardhat run scripts/deploy.js --network localhost
```

### 3. Start the frontend server

```bash
node frontend/server.js
```

Open: **http://127.0.0.1:4173/frontend/**

---

## Frontend Evidence Console

### Workflow

1. **Upload an image** — drag and drop or browse (JPG/PNG/WEBP, max 15 MB).
2. Optionally paste a **public source URL** if you know where the image came from.
3. Click **Analyze evidence** — the pipeline runs automatically.
4. Results show face similarity, source attribution, SHA-256 fingerprint, and blockchain record.
5. Use **Load case-001** or **Load case-002** to view preserved demo cases instantly.
6. **Clear workspace** resets the current session without deleting saved artifacts.

### Saved Cases and Page Refresh

- Session state (selected file preview, last loaded case, last result) is stored in `sessionStorage`.
- Refreshing the page restores the last result without making any new API calls.
- Each new unique image is assigned a hash-based case ID (`case-<8hex>`).
- Uploading the same image twice reuses the existing preserved case automatically.

### Clear Workspace

Clicking **Clear workspace** resets the input, previews, source URL, and result panels. It does **not** delete any artifact files or blockchain records. Historical evidence in `artifacts/` is always preserved.

---

## API Routes (server.js)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/cases` | List all completed case IDs |
| `GET` | `/api/case/:id` | Return preserved case result JSON |
| `POST` | `/api/analyze` | Run full pipeline on uploaded image |
| `GET` | `/artifacts/*` | Static artifact files (images, metadata) |
| `GET` | `/frontend/*` | Static frontend assets |

### POST /api/analyze

Request body (JSON):
```json
{
  "useSample": false,
  "type": "image/jpeg",
  "data": "<base64-encoded image>",
  "sourceUrl": "https://example.com/optional"
}
```

The server first checks whether the uploaded image's SHA-256 matches any existing `input.jpg` in `artifacts/`. If a match is found, the existing case result is returned immediately without running the pipeline.

---

## CLI Reference

```bash
# SHA-256 fingerprint of any file
python python/main.py hash <file>

# Face detection and embedding
python python/main.py face <image>

# Compare two face images
python python/main.py compare <image-a> <image-b>

# Rank local candidate images by similarity to a reference
python python/main.py rank <reference> <candidate1> <candidate2> ...

# Search (dry-run — no API call)
python python/main.py search --image-path <file> --dry-run

# End-to-end candidate selection
python python/main.py select-candidate <image> --case case-001 --type all --dry-run

# Anchor selected artifact on blockchain
python python/main.py anchor --case case-001

# Verify fingerprint against blockchain
python python/main.py verify --case case-001
```

---

## SerpApi Caching and Quota Protection

The search layer enforces strict zero-waste rules:

- **No automatic searches.** Startup, page refresh, clear workspace, and loading existing cases never contact SerpApi.
- **Cache-first.** Successful responses are cached locally (`LENS_CACHE_ENABLED=true`) with a configurable TTL (`LENS_CACHE_TTL=604800`, i.e. 7 days).
- **Artifact deduplication.** Uploading the same image twice reuses the existing case without any API call.
- **Dry-run mode.** `--dry-run` validates all parameters without network activity.
- **SSRF protection.** Private IPs, loopback, and cloud metadata addresses are blocked.

---

## SHA-256 and Blockchain Verification

### Registration

1. SHA-256 is computed over the **exact raw bytes** of the preserved candidate image.
2. The 32-byte hash is submitted to `ContentRegistry.registerContent(bytes32, sourceUrl)`.
3. The transaction hash and block number are recorded in `anchoring_metadata.json`.
4. If the fingerprint is already registered, the existing record is reused — no second transaction.

### Verification

1. The stored `bytes32` hash is retrieved from the blockchain via the transaction hash or direct storage lookup.
2. SHA-256 is recomputed from the local artifact file.
3. If `recomputed == on-chain`, the result is **BLOCKCHAIN VERIFICATION PASSED**.
4. A single changed byte produces a completely different SHA-256 and yields **VERIFICATION FAILED**.

### What Blockchain Registration Proves (and Does Not Prove)

- ✅ A fingerprint of this exact file was recorded at this transaction timestamp.
- ✅ The file has not been altered since registration (verified by hash comparison).
- ❌ The blockchain does not prove who owns the image.
- ❌ It does not prove where the image was originally published.
- ❌ ArcFace similarity does not prove legal identity.

### Local Hardhat Limitations

The default deployment uses a local Hardhat node (`chainId 31337`). This node:
- Resets when stopped (all transactions lost unless you restart with the same state).
- Is not publicly accessible or independently verifiable.
- Provides correct functional demonstration but is not equivalent to a public testnet.

---

## Automated Tests

### Python

```bash
# All tests
python -m unittest discover -s tests

# Individual file
python -m unittest tests.test_hashing
python -m unittest tests.test_system_regression
```

Tests use mocks and fixtures. No SerpApi credits are consumed. All 68 tests pass.

### Blockchain (Hardhat)

```bash
cd blockchain
npx hardhat test
```

Covers: registration, duplicate rejection, zero-hash rejection, event emission, and `getRecord` retrieval.

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `SERPAPI_KEY` | _(required for live search)_ | SerpApi API key |
| `INSIGHTFACE_MODEL` | `buffalo_l` | InsightFace model pack |
| `FACE_SIMILARITY_THRESHOLD` | `0.40` | Minimum cosine similarity to qualify a candidate |
| `MAX_CANDIDATES` | `20` | Maximum candidates to download and evaluate |
| `LENS_CACHE_ENABLED` | `true` | Cache SerpApi responses locally |
| `LENS_CACHE_TTL` | `604800` | Cache TTL in seconds (7 days) |
| `MAX_IMAGE_DOWNLOAD_BYTES` | `15728640` | Max candidate download size (15 MB) |
| `RPC_URL` | `http://127.0.0.1:8545` | Blockchain RPC endpoint |
| `PRIVATE_KEY` | _(blank for local)_ | Wallet private key for signing transactions |
| `CONTRACT_ADDRESS` | _(from deployments/)_ | Deployed ContentRegistry address |
| `CHAIN_ID` | `31337` | Chain ID (31337=Hardhat, 11155111=Sepolia) |

---

## Common Failures and Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `SERPAPI_KEY is not configured` | Missing `.env` entry | Add `SERPAPI_KEY=…` to `.env` |
| `No face detected` | Input image has no clear face | Use a front-facing, well-lit photograph |
| `No candidate passed threshold` | Search returned low-similarity results | Lower `FACE_SIMILARITY_THRESHOLD` or try a different image |
| `cannot reach the blockchain` | Hardhat node not running | Run `npx hardhat node` in `blockchain/` |
| `contract not compiled yet` | Solidity not built | Run `npx hardhat compile` in `blockchain/` |
| `Case artifacts incomplete` | Pipeline failed partway through | Re-run `select-candidate` + `anchor` + `verify` for the case |
| Windows Unicode crash | Old `cp1252` console encoding | Fixed: `PYTHONIOENCODING=utf-8` is forced by the server |
