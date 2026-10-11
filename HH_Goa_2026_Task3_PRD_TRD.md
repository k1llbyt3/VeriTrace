# HH Goa 2026 --- Task 3

# Face Identification & Blockchain Verification

## Product Requirements Document (PRD) + Technical Requirements Document (TRD) + Supporting Documentation

**Document version:** 1.0\
**Status:** MVP / Challenge Submission\
**Primary objective:** Build a working end-to-end pipeline that
identifies a person/image from an input face, discovers genuine online
content, ranks candidate matches, fingerprints the selected digital
artifact with SHA-256, records the fingerprint on a blockchain, and
later verifies the artifact against the on-chain fingerprint.

------------------------------------------------------------------------

# 1. Executive Summary

The project is an end-to-end proof and verification pipeline.

A user supplies an image containing a face. The system:

1.  Detects the face using InsightFace SCRFD.
2.  Generates an ArcFace face embedding.
3.  Performs a genuine reverse-image/web search using Google Lens
    through SerpApi.
4.  Collects real candidate images/posts and their source URLs.
5.  Downloads accessible candidate images.
6.  Detects faces in candidate images and generates ArcFace embeddings.
7.  Calculates cosine similarity between the input face and candidate
    faces.
8.  Ranks candidates and selects the strongest valid match using a
    documented threshold.
9.  Preserves the exact discovered artifact used for registration.
10. Calculates a SHA-256 cryptographic fingerprint.
11. Registers that fingerprint in a Solidity smart contract on an
    EVM-compatible blockchain.
12. Records the transaction hash and block information.
13. Later retrieves the stored hash.
14. Recomputes SHA-256 from the verification artifact.
15. Compares the two hashes.
16. Displays `BLOCKCHAIN VERIFICATION PASSED` or `VERIFICATION FAILED`.

The system deliberately separates three different concepts:

-   **ArcFace:** face similarity / identity evidence.
-   **SHA-256:** exact digital-file integrity.
-   **Blockchain:** independently verifiable record of the fingerprint.

------------------------------------------------------------------------

# 2. Product Requirements Document (PRD)

## 2.1 Problem Statement

A face-containing image may appear online in multiple locations. Merely
finding a similar image is not enough to provide a verifiable record of
the discovered digital artifact.

The challenge requires a pipeline that combines:

-   face identification,
-   genuine web/social-media discovery,
-   evidence ranking,
-   cryptographic fingerprinting,
-   blockchain registration,
-   and later verification.

The product should demonstrate the complete chain rather than isolated
technologies.

------------------------------------------------------------------------

## 2.2 Product Goal

Build a minimal, reliable, demonstrable application that can answer:

> "Given an input face image, can we discover genuine online content
> containing the matching person/image, select the strongest candidate,
> record an exact fingerprint of that discovered artifact on-chain, and
> later prove whether the same artifact has been preserved?"

------------------------------------------------------------------------

## 2.3 Target Users

### Primary

-   Hackathon judges
-   Developers evaluating the prototype
-   Researchers/testing teams

### Secondary

-   Content verification teams
-   Digital-forensics learners
-   Developers interested in blockchain-backed evidence

------------------------------------------------------------------------

## 2.4 User Story

### Registration flow

> As a user, I upload a face image. I want the system to find relevant
> real online content, identify the strongest matching result,
> fingerprint the selected artifact, and record the fingerprint on
> blockchain so that it can be verified later.

### Verification flow

> As a verifier, I want to provide the preserved artifact and blockchain
> transaction/record information so that the system can recalculate its
> SHA-256 hash and determine whether it exactly matches the recorded
> fingerprint.

------------------------------------------------------------------------

## 2.5 Functional Requirements

### FR-01 --- Input Image

The application shall accept a local image file containing at least one
detectable face.

Supported initial formats:

-   JPG/JPEG
-   PNG
-   WEBP

The system shall reject unreadable or unsupported files.

------------------------------------------------------------------------

### FR-02 --- Face Detection

The system shall use InsightFace with SCRFD or the corresponding
supported face detector.

It shall:

-   detect one or more faces,
-   select the intended face according to a documented rule,
-   expose detection confidence,
-   handle the no-face case gracefully.

------------------------------------------------------------------------

### FR-03 --- Face Embedding

The system shall generate an ArcFace embedding for the selected face.

The embedding should be normalized before similarity comparison.

Output should include:

-   embedding dimension,
-   detection confidence,
-   selected face information.

Embeddings themselves do not need to be stored on-chain.

------------------------------------------------------------------------

### FR-04 --- Genuine Reverse Image Search

The system shall perform an actual external search rather than using a
hardcoded URL.

Preferred MVP:

-   SerpApi
-   Google Lens endpoint

The search should provide the input image or an accessible hosted image
URL according to the API requirements.

The system should request/use:

-   exact matches where available,
-   visual matches where available,
-   titles,
-   source/domain,
-   image URLs,
-   result URLs.

------------------------------------------------------------------------

### FR-05 --- Candidate Collection

The system shall collect candidate results from the search response.

Each candidate should contain, where available:

``` text
candidate_id
title
source_url
image_url
domain
search_type
search_rank
```

The system shall discard candidates for which no usable image can be
obtained.

------------------------------------------------------------------------

### FR-06 --- Candidate Face Analysis

For each accessible candidate image, the system shall:

1.  Download the image.
2.  Detect faces.
3.  Generate ArcFace embeddings.
4.  Compare candidate face embeddings against the input embedding.

If a candidate contains multiple faces, the system shall compare the
input embedding against each detected face and retain the highest valid
similarity for that candidate.

------------------------------------------------------------------------

### FR-07 --- Cosine Similarity

The system shall calculate cosine similarity between the normalized
input face embedding and candidate face embeddings.

Conceptually:

``` text
similarity = cosine(input_embedding, candidate_embedding)
```

Higher similarity means greater facial embedding similarity.

The exact threshold shall be configurable through
environment/configuration.

The threshold must be documented and described as an empirical demo
threshold rather than an absolute identity guarantee.

------------------------------------------------------------------------

### FR-08 --- Candidate Ranking

Candidates shall be ranked using evidence including:

-   face similarity score,
-   search rank,
-   source availability,
-   successful image retrieval,
-   number of detected faces.

The MVP must expose the strongest candidate and enough evidence to
understand why it was selected.

Recommended output:

``` text
Candidate URL
Source/domain
Face similarity
Search position
Detection confidence
Image retrieval status
Selection decision
```

------------------------------------------------------------------------

### FR-09 --- Match Selection

The system shall select a candidate only when it passes the configured
similarity threshold.

If no candidate passes the threshold:

``` text
NO VALID MATCH FOUND
```

The system must not invent or substitute a URL.

------------------------------------------------------------------------

### FR-10 --- Evidence Preservation

The exact digital artifact selected for blockchain registration shall be
preserved locally.

Recommended structure:

``` text
artifacts/
└── <case_id>/
    ├── input.jpg
    ├── discovered.jpg
    ├── metadata.json
    └── hash.txt
```

The artifact used for hashing must be clearly identified.

------------------------------------------------------------------------

### FR-11 --- SHA-256 Fingerprinting

The system shall calculate SHA-256 over the exact bytes of the selected
artifact.

Conceptual flow:

``` text
discovered.jpg
     ↓
SHA-256
     ↓
contentHash
```

The system shall display:

-   algorithm: SHA-256
-   hash
-   file name
-   file size
-   timestamp

------------------------------------------------------------------------

### FR-12 --- Blockchain Registration

The system shall register the content hash on an EVM-compatible
blockchain.

Preferred smart contract:

``` solidity
ContentRegistry
```

Recommended function:

``` solidity
registerContent(bytes32 contentHash, string sourceUrl)
```

The contract should provide a method/event to retrieve the registration.

The system shall record:

-   transaction hash,
-   block number,
-   content hash,
-   source URL,
-   registration timestamp if available.

------------------------------------------------------------------------

### FR-13 --- Verification

The verification process shall:

1.  Retrieve the registered on-chain hash.
2.  Obtain the exact verification artifact.
3.  Recalculate SHA-256.
4.  Compare:

``` text
recomputedHash === blockchainHash
```

If equal:

``` text
BLOCKCHAIN VERIFICATION PASSED
```

If different:

``` text
VERIFICATION FAILED
```

------------------------------------------------------------------------

### FR-14 --- Tampering Demonstration

The demo should include a negative test.

Example:

``` text
Original artifact
    ↓
SHA-256
    ↓
ABC123...

Modified artifact
    ↓
SHA-256
    ↓
XYZ789...

ABC123 != XYZ789
    ↓
VERIFICATION FAILED
```

------------------------------------------------------------------------

## 2.6 Non-Functional Requirements

### NFR-01 --- Reproducibility

The project must provide setup instructions sufficient for another
developer to reproduce the MVP.

### NFR-02 --- Transparency

The application must not claim that ArcFace proves legal identity or
that blockchain proves ownership of the image.

### NFR-03 --- Security

API keys, private keys, RPC URLs and secrets shall be stored in
environment variables and never committed to Git.

### NFR-04 --- Error Handling

The system shall handle:

-   no face,
-   multiple faces,
-   no search results,
-   API failure,
-   image download failure,
-   invalid image,
-   low similarity,
-   blockchain transaction failure,
-   verification mismatch.

### NFR-05 --- Demonstrability

The full flow should be executable from a simple CLI or minimal local
UI.

A full website is not required.

### NFR-06 --- Logging

The system should log each major stage and its status.

------------------------------------------------------------------------

# 3. Technical Requirements Document (TRD)

## 3.1 Recommended Architecture

``` text
                    INPUT
                      │
                      ▼
              ┌───────────────┐
              │ Input Image   │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ SCRFD Detector│
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ ArcFace        │
              │ Embedding      │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ Google Lens   │
              │ via SerpApi    │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ Candidate     │
              │ Collection    │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ Download      │
              │ Candidate Img │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ SCRFD +        │
              │ ArcFace        │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ Cosine         │
              │ Similarity     │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ Rank & Select │
              │ Best Candidate│
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ Preserve      │
              │ Exact Artifact│
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ SHA-256       │
              └───────┬───────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ Solidity ContentRegistry    │
        │ EVM Blockchain              │
        └─────────────┬───────────────┘
                      │
                      ▼
              Transaction Hash
                      │
                      ▼
                Later Verify
                      │
                      ▼
              Retrieve On-chain Hash
                      │
                      ▼
              SHA-256 Again
                      │
                      ▼
                 Compare
                 /      \
                /        \
             MATCH      DIFFERENT
               │            │
               ▼            ▼
           VERIFIED       FAILED
```

------------------------------------------------------------------------

# 4. Technology Stack

## 4.1 AI / Computer Vision

### Python

Primary programming language for the face/search pipeline.

### InsightFace

Used for:

-   face detection,
-   face alignment,
-   face recognition embeddings.

Preferred pipeline:

``` text
SCRFD → face detection
ArcFace → face embedding
```

### OpenCV / Pillow

Used for:

-   image loading,
-   resizing,
-   format handling,
-   image validation.

### NumPy

Used for:

-   vectors,
-   normalization,
-   cosine similarity,
-   numerical operations.

------------------------------------------------------------------------

## 4.2 Web Search

### SerpApi Google Lens

Preferred MVP reverse-image-search service.

Purpose:

``` text
Input image
    ↓
Google Lens
    ↓
Exact / visual matches
    ↓
Candidate URLs + images + metadata
```

### Optional Google Search API

Can be used after Lens discovery to search:

-   discovered names,
-   captions,
-   domains,
-   candidate URLs,
-   related text.

------------------------------------------------------------------------

## 4.3 Cryptography

Python standard library:

``` python
hashlib
```

Primary algorithm:

``` text
SHA-256
```

------------------------------------------------------------------------

## 4.4 Blockchain

### Solidity

Smart contract language.

### Hardhat

Recommended for:

-   compilation,
-   testing,
-   deployment,
-   local development.

### ethers.js

Used by the blockchain interaction layer to:

-   connect to RPC,
-   load contract,
-   submit transactions,
-   wait for confirmation,
-   retrieve contract data.

### Blockchain

Development options:

1.  Local Hardhat/Anvil node.
2.  Public Ethereum Sepolia testnet.

A public testnet is preferred for the final demo if practical.

------------------------------------------------------------------------

# 5. Smart Contract Specification

## 5.1 Contract Name

``` text
ContentRegistry
```

## 5.2 Suggested Data Model

``` solidity
struct ContentRecord {
    bytes32 contentHash;
    string sourceUrl;
    uint256 registeredAt;
    address registrant;
}
```

The contract can map a content hash or record ID to the registration.

------------------------------------------------------------------------

## 5.3 Suggested Function

``` solidity
function registerContent(
    bytes32 contentHash,
    string calldata sourceUrl
) external
```

------------------------------------------------------------------------

## 5.4 Suggested Event

``` solidity
event ContentRegistered(
    bytes32 indexed contentHash,
    string sourceUrl,
    address indexed registrant,
    uint256 timestamp
);
```

------------------------------------------------------------------------

## 5.5 Important Blockchain Rule

Do not store the actual image on-chain.

Store the fingerprint and minimal metadata.

``` text
IMAGE
  ❌ blockchain

SHA-256 HASH
  ✅ blockchain

SOURCE URL
  ✅ optional

TIMESTAMP
  ✅ useful

REGISTRANT
  ✅ useful
```

This keeps the blockchain transaction small and avoids unnecessary
exposure of the image.

------------------------------------------------------------------------

# 6. Data Flow

## 6.1 Input

``` json
{
  "file": "input.jpg"
}
```

## 6.2 Face Analysis

Example conceptual output:

``` json
{
  "face_detected": true,
  "face_count": 1,
  "detection_confidence": 0.98,
  "embedding_generated": true
}
```

------------------------------------------------------------------------

## 6.3 Search Result

``` json
{
  "title": "Example Post",
  "source_url": "https://example.com/post",
  "image_url": "https://example.com/image.jpg",
  "domain": "example.com"
}
```

------------------------------------------------------------------------

## 6.4 Candidate Scoring

``` json
{
  "candidate_url": "https://example.com/post",
  "face_similarity": 0.82,
  "search_rank": 1,
  "face_detected": true,
  "passes_threshold": true
}
```

------------------------------------------------------------------------

## 6.5 Blockchain Registration

``` json
{
  "content_hash": "0x...",
  "source_url": "https://example.com/post",
  "transaction_hash": "0x...",
  "block_number": 1234567
}
```

------------------------------------------------------------------------

## 6.6 Verification

``` json
{
  "blockchain_hash": "0x...",
  "recomputed_hash": "0x...",
  "match": true,
  "status": "BLOCKCHAIN VERIFICATION PASSED"
}
```

------------------------------------------------------------------------

# 7. Repository Structure

Recommended repository:

``` text
face-blockchain-verification/
│
├── README.md
├── PRD_TRD.md
├── .env.example
├── .gitignore
├── requirements.txt
├── package.json
│
├── python/
│   ├── main.py
│   ├── face/
│   │   ├── detector.py
│   │   ├── embedding.py
│   │   └── similarity.py
│   │
│   ├── search/
│   │   ├── lens.py
│   │   ├── candidates.py
│   │   └── downloader.py
│   │
│   ├── evidence/
│   │   ├── artifact.py
│   │   └── hashing.py
│   │
│   └── config.py
│
├── blockchain/
│   ├── contracts/
│   │   └── ContentRegistry.sol
│   ├── scripts/
│   │   └── deploy.js
│   ├── test/
│   │   └── ContentRegistry.test.js
│   ├── hardhat.config.js
│   └── package.json
│
├── artifacts/
│   └── .gitkeep
│
├── tests/
│   ├── test_hashing.py
│   ├── test_similarity.py
│   └── test_pipeline.py
│
└── docs/
    ├── ARCHITECTURE.md
    ├── THREAT_MODEL.md
    ├── LIMITATIONS.md
    ├── DEMO_SCRIPT.md
    └── API.md
```

------------------------------------------------------------------------

# 8. Environment Configuration

Example `.env.example`:

``` text
SERPAPI_KEY=your_serpapi_key

RPC_URL=your_rpc_url
PRIVATE_KEY=your_test_wallet_private_key
CONTRACT_ADDRESS=deployed_contract_address
CHAIN_ID=11155111
```

Never commit the real `.env`.

Add:

``` text
.env
```

to `.gitignore`.

------------------------------------------------------------------------

# 9. Installation Requirements

## Python

Recommended:

``` text
Python 3.10+
```

Install core dependencies:

``` bash
pip install insightface opencv-python pillow numpy requests python-dotenv
```

Additional dependencies may be required depending on the selected
InsightFace runtime/model installation.

------------------------------------------------------------------------

## Node.js

Recommended:

``` text
Node.js 20+
```

Install:

``` bash
npm install
```

Recommended blockchain packages:

``` text
hardhat
ethers
dotenv
```

------------------------------------------------------------------------

# 10. Configuration Requirements

The project requires:

### Search API

A SerpApi API key.

### Blockchain RPC

One of:

-   local Hardhat node,
-   local Anvil node,
-   Sepolia RPC provider.

### Test Wallet

A dedicated development/test wallet.

Never use a wallet containing valuable funds.

### Testnet Funds

For Sepolia, obtain test ETH from a supported faucet.

------------------------------------------------------------------------

# 11. CLI Design

A simple CLI is sufficient.

## Registration

Example:

``` bash
python main.py register --image input.jpg
```

Expected stages:

``` text
[1/9] Loading image
[2/9] Detecting face
[3/9] Generating ArcFace embedding
[4/9] Searching Google Lens
[5/9] Collecting candidates
[6/9] Ranking candidates
[7/9] Hashing selected artifact
[8/9] Registering on blockchain
[9/9] Registration complete
```

------------------------------------------------------------------------

## Verification

Example:

``` bash
python main.py verify --artifact artifacts/case-001/discovered.jpg --tx 0x...
```

Expected:

``` text
Blockchain hash : abc123...
Computed hash   : abc123...

================================
BLOCKCHAIN VERIFICATION PASSED
================================
```

------------------------------------------------------------------------

# 12. Similarity Threshold

The similarity threshold must be configurable.

Example:

``` text
FACE_SIMILARITY_THRESHOLD=0.70
```

The actual value must be calibrated experimentally with the selected
InsightFace model and test images.

Important:

> A similarity score is evidence of embedding similarity, not a
> universal proof of human identity.

The README should clearly document:

-   model used,
-   threshold used,
-   test examples,
-   false-positive/false-negative limitations.

------------------------------------------------------------------------

# 13. Hashing and Canonicalization

## 13.1 Exact-Bytes Strategy

For the safest MVP:

``` text
Downloaded artifact
       ↓
Preserve exact bytes
       ↓
SHA-256
       ↓
Blockchain
```

During verification, use the same preserved bytes.

This is the simplest reproducible demo.

------------------------------------------------------------------------

## 13.2 Why Raw Hashes Can Change

A website may dynamically:

-   resize images,
-   recompress JPEGs,
-   change metadata,
-   convert formats,
-   serve different versions.

Therefore:

``` text
Same visual image
      ≠
Same raw file bytes
```

and therefore:

``` text
Same visual image
      ≠
Same SHA-256
```

if the file representation changes.

------------------------------------------------------------------------

## 13.3 Optional Canonicalization

A more advanced version can define a deterministic canonical
representation.

Example:

``` text
download
 ↓
decode
 ↓
resize according to fixed rule
 ↓
convert to fixed format
 ↓
remove metadata
 ↓
encode deterministically
 ↓
SHA-256
```

If canonicalization is used, the exact procedure must be documented and
applied identically during registration and verification.

For the hackathon MVP, preserving the exact downloaded artifact is
recommended.

------------------------------------------------------------------------

# 14. Security and Privacy Requirements

## 14.1 Private Keys

Private keys must never be hardcoded.

Bad:

``` javascript
const privateKey = "actual-private-key";
```

Good:

``` text
PRIVATE_KEY=<environment variable>
```

------------------------------------------------------------------------

## 14.2 API Keys

Never commit:

``` text
SERPAPI_KEY
```

to GitHub.

------------------------------------------------------------------------

## 14.3 Personal Data

Face images and embeddings can represent sensitive biometric
information.

The MVP should:

-   process data only for the challenge purpose,
-   avoid unnecessary retention,
-   avoid publishing private images,
-   explain limitations in the README.

------------------------------------------------------------------------

## 14.4 Blockchain Privacy

Do not put the face image or embedding directly on-chain.

The chain should contain the minimum necessary proof information.

------------------------------------------------------------------------

# 15. Threat Model

## Threat 1 --- Modified Artifact

Attacker changes the downloaded image.

Expected result:

``` text
SHA-256 changes
      ↓
Verification fails
```

------------------------------------------------------------------------

## Threat 2 --- Different Image With Similar Face

A different photo of the same person may have a high ArcFace similarity.

Expected:

``` text
ArcFace similarity → potentially high
SHA-256 → different
```

This demonstrates why face similarity and file integrity are separate.

------------------------------------------------------------------------

## Threat 3 --- Search Result Manipulation

Search results may contain:

-   incorrect matches,
-   duplicates,
-   unrelated visually similar images,
-   inaccessible pages.

Mitigation:

-   rank candidates,
-   detect/compare faces,
-   show evidence,
-   require threshold,
-   never hardcode the final URL.

------------------------------------------------------------------------

## Threat 4 --- Dynamic Web Content

The source website may change the image served at a URL.

Mitigation:

-   preserve the exact artifact,
-   record source URL,
-   record retrieval timestamp,
-   optionally store additional metadata.

------------------------------------------------------------------------

# 16. Limitations

The MVP must explicitly state:

1.  Reverse-image search quality depends on the external search
    provider.
2.  Some social-media pages may block automated access.
3.  Not every search result will expose a downloadable image.
4.  Face embedding similarity is not absolute proof of real-world
    identity.
5.  SHA-256 verifies exact digital content, not visual equivalence.
6.  Blockchain records the fingerprint but does not prove that the
    original image was truthful.
7.  A blockchain timestamp does not by itself prove ownership or
    copyright.
8.  Public blockchain transactions are observable.
9.  External APIs may have rate limits or costs.
10. The same visual image may have different SHA-256 hashes if its file
    bytes differ.

------------------------------------------------------------------------

# 17. Test Plan

## Test Case 1 --- Valid Face

**Input:** clear image with one face.

Expected:

``` text
Face detected
Embedding generated
Search performed
Candidates ranked
```

------------------------------------------------------------------------

## Test Case 2 --- No Face

**Input:** image without a face.

Expected:

``` text
ERROR: No face detected
```

------------------------------------------------------------------------

## Test Case 3 --- Multiple Faces

**Input:** group photograph.

Expected:

-   detect multiple faces,
-   apply documented selection rule,
-   or request/select the target face.

------------------------------------------------------------------------

## Test Case 4 --- Low Similarity

Expected:

``` text
NO VALID MATCH FOUND
```

when no candidate exceeds the configured threshold.

------------------------------------------------------------------------

## Test Case 5 --- Successful Registration

Expected:

``` text
SHA-256 generated
Transaction submitted
Transaction confirmed
TXID displayed
```

------------------------------------------------------------------------

## Test Case 6 --- Successful Verification

Expected:

``` text
Blockchain hash == computed hash

BLOCKCHAIN VERIFICATION PASSED
```

------------------------------------------------------------------------

## Test Case 7 --- Modified Artifact

Modify one byte/pixel of the preserved artifact.

Expected:

``` text
Blockchain hash != computed hash

VERIFICATION FAILED
```

------------------------------------------------------------------------

# 18. Demo Script

The final recording should show the complete working pipeline.

## Scene 1 --- Input

Show:

``` text
Input image: input.jpg
```

------------------------------------------------------------------------

## Scene 2 --- Face Detection

Show:

``` text
SCRFD
Face detected
Confidence: ...
```

------------------------------------------------------------------------

## Scene 3 --- Face Embedding

Show:

``` text
ArcFace embedding generated
```

Do not dump the entire embedding if it makes the demo difficult to
understand.

------------------------------------------------------------------------

## Scene 4 --- Genuine Search

Show:

``` text
Google Lens / SerpApi request
```

Then show real search results.

------------------------------------------------------------------------

## Scene 5 --- Candidate Ranking

Show something like:

``` text
Candidate 1
URL: ...
Similarity: 0.84

Candidate 2
URL: ...
Similarity: 0.71

Candidate 3
URL: ...
Similarity: 0.42

Selected Candidate: Candidate 1
```

------------------------------------------------------------------------

## Scene 6 --- SHA-256

Show:

``` text
Artifact:
discovered.jpg

SHA-256:
abc123...
```

------------------------------------------------------------------------

## Scene 7 --- Blockchain

Show:

``` text
Registering content hash...

Transaction:
0x...

Block:
...

Confirmed
```

------------------------------------------------------------------------

## Scene 8 --- Verification

Show:

``` text
On-chain hash:
abc123...

Recalculated hash:
abc123...

BLOCKCHAIN VERIFICATION PASSED
```

------------------------------------------------------------------------

## Scene 9 --- Tampering

Modify the artifact and run verification again.

Show:

``` text
On-chain hash:
abc123...

Recalculated hash:
xyz789...

VERIFICATION FAILED
```

This final negative test strongly demonstrates that the blockchain
fingerprint is actually being checked.

------------------------------------------------------------------------

# 19. README Requirements

The repository README should contain:

## Project Overview

Explain the challenge and purpose.

## Architecture

Include the complete pipeline diagram.

## Concepts for Beginners

Explain:

-   face detection,
-   face embedding,
-   ArcFace,
-   cosine similarity,
-   reverse image search,
-   hash,
-   SHA-256,
-   blockchain,
-   smart contract,
-   transaction,
-   transaction hash,
-   testnet.

## Installation

Provide exact commands.

## API Configuration

Explain `.env`.

## Model Information

Document the InsightFace model/pipeline.

## Search Configuration

Explain SerpApi Google Lens setup.

## Blockchain Setup

Explain:

-   local blockchain,
-   Sepolia,
-   RPC provider,
-   test wallet,
-   deployment,
-   contract address.

## Running the Pipeline

Show registration and verification commands.

## Verification

Explain successful and failed cases.

## Limitations

Include all important limitations.

## Demo

Describe the screen recording flow.

------------------------------------------------------------------------

# 20. Supporting Documents

The repository should ideally include:

### `PRD_TRD.md`

Product and technical requirements.

### `ARCHITECTURE.md`

Detailed architecture and data flow.

### `API.md`

External APIs, request/response formats and configuration.

### `THREAT_MODEL.md`

Security assumptions, threats and mitigations.

### `LIMITATIONS.md`

Known limitations and responsible claims.

### `DEMO_SCRIPT.md`

Exact screen-recording sequence.

### `DECISIONS.md`

Important engineering decisions and why they were made.

------------------------------------------------------------------------

# 21. Engineering Decisions

## Decision 1 --- Python for AI Pipeline

Reason:

-   strong computer-vision ecosystem,
-   InsightFace support,
-   easy NumPy/OpenCV integration,
-   fast prototyping.

------------------------------------------------------------------------

## Decision 2 --- Google Lens via SerpApi

Reason:

-   genuine reverse-image search,
-   real web results,
-   exact/visual match support,
-   avoids hardcoding a social-media URL.

------------------------------------------------------------------------

## Decision 3 --- SHA-256 Locally

Reason:

-   built into Python,
-   simple,
-   deterministic,
-   cryptographically strong for integrity fingerprinting.

------------------------------------------------------------------------

## Decision 4 --- Solidity Contract

Reason:

-   simple EVM-compatible implementation,
-   easy retrieval,
-   easy demonstration,
-   compatible with ethers.js.

------------------------------------------------------------------------

## Decision 5 --- Sepolia or Local EVM

Reason:

-   avoids mainnet cost,
-   suitable for development,
-   publicly verifiable if Sepolia is used.

------------------------------------------------------------------------

# 22. MVP Definition of Done

The project is considered complete when all of the following work:

-   [ ] Input image loads.
-   [ ] Face is detected with SCRFD.
-   [ ] ArcFace embedding is generated.
-   [ ] Genuine reverse-image search is performed.
-   [ ] Real candidate URLs are returned.
-   [ ] Candidate images are downloaded when accessible.
-   [ ] Candidate faces are detected.
-   [ ] Candidate embeddings are generated.
-   [ ] Cosine similarity is calculated.
-   [ ] Candidates are ranked.
-   [ ] A documented threshold is applied.
-   [ ] Best valid candidate is selected.
-   [ ] Exact artifact is preserved.
-   [ ] SHA-256 is calculated.
-   [ ] Smart contract is deployed.
-   [ ] Hash is registered on-chain.
-   [ ] Transaction hash is recorded.
-   [ ] On-chain hash is retrievable.
-   [ ] Verification recalculates SHA-256.
-   [ ] Matching artifact produces PASSED.
-   [ ] Modified artifact produces FAILED.
-   [ ] README contains setup instructions.
-   [ ] `.env.example` is provided.
-   [ ] No secrets are committed.
-   [ ] Demo recording shows the complete flow.

------------------------------------------------------------------------

# 23. Final Conceptual Explanation

The entire project can be explained in three sentences:

> **ArcFace says:** "The face in this candidate image is sufficiently
> similar to the face in the input image."

> **SHA-256 says:** "These exact digital bytes are the same as the bytes
> whose fingerprint was recorded."

> **Blockchain says:** "This fingerprint was recorded in a publicly
> verifiable, tamper-resistant ledger."

Therefore:

``` text
FACE SIMILARITY
      +
DIGITAL INTEGRITY
      +
BLOCKCHAIN RECORD
      =
END-TO-END VERIFICATION PIPELINE
```

The system should never claim that these three technologies prove the
same thing. Their value comes from combining their separate strengths.

------------------------------------------------------------------------

# 24. Recommended Implementation Order

For a beginner, implement in this exact order:

``` text
Phase 1
Python basics
    ↓
Phase 2
Load image
    ↓
Phase 3
SHA-256 a local image
    ↓
Phase 4
InsightFace face detection
    ↓
Phase 5
ArcFace embedding
    ↓
Phase 6
Cosine similarity between two local images
    ↓
Phase 7
SerpApi Google Lens search
    ↓
Phase 8
Download and rank candidate images
    ↓
Phase 9
Build Solidity ContentRegistry
    ↓
Phase 10
Deploy locally
    ↓
Phase 11
Register SHA-256 on blockchain
    ↓
Phase 12
Retrieve + verify hash
    ↓
Phase 13
Connect everything
    ↓
Phase 14
Demo + README
```

------------------------------------------------------------------------

## 24.1 Implemented Case Walkthrough (case-001)

The repository implements the architecture above with one CLI workflow.  The
case evidence directory is the hand-off point between candidate selection,
anchoring, and later verification:

``` text
artifacts/case-001/
    input.jpg                     reference image
    candidate-001.jpg             selected, preserved downloaded bytes
    selection_metadata.json       selection evidence and ArcFace score
    anchoring_metadata.json       SHA-256 and blockchain receipt (after anchor)
```

`selection_metadata.json` is created by `select-candidate`.  It records each
candidate's download and face-analysis outcome.  A candidate is selected only
when it has a detected face and its best ArcFace cosine similarity passes
`FACE_SIMILARITY_THRESHOLD`; the highest qualifying score wins.  A low-score,
unreadable, or no-face candidate is never selected.

### What each verification layer means

- **ArcFace similarity** is visual face-similarity evidence used to rank and
  select search candidates. It is not proof of a person's legal identity.
- **SHA-256** fingerprints the exact downloaded file bytes. Re-saving,
  resizing, recompressing, editing metadata, or changing one byte produces a
  different value, even when two images look the same.
- **ContentRegistry on a blockchain** stores that fingerprint, its source URL,
  timestamp, and registrant. It provides a tamper-resistant record that a
  fingerprint was registered; it does not prove ownership or truthfulness.

`BLOCKCHAIN VERIFICATION PASSED` means the supplied artifact is byte-for-byte
identical to the hash retrieved from `ContentRegistry`. `VERIFICATION FAILED`
means the bytes are different. Neither verdict measures visual similarity.

### Required configuration

Copy `.env.example` to `.env` and set only the values needed for the command
you are running. Never commit `.env`.

- `SERPAPI_KEY`: required only for a new Google Lens search.
- `INSIGHTFACE_MODEL`, `DET_SIZE`, `FACE_SIMILARITY_THRESHOLD`, and
  `MAX_CANDIDATES`: face-pipeline settings.
- `RPC_URL`: local Hardhat node or an EVM testnet RPC endpoint.
- `PRIVATE_KEY`: required for a public/testnet transaction; leave blank for a
  local Hardhat node's unlocked development account.
- `CONTRACT_ADDRESS`: deployed `ContentRegistry` address. A local deployment
  is also discovered from `blockchain/deployments/localhost.json`.
- `CHAIN_ID`: network ID (`31337` for local Hardhat; `11155111` for Sepolia).

### Reproduce the complete local case-001 flow

From the repository root, first install dependencies, then use two terminals:

``` powershell
# Terminal 1: start the local EVM chain
cd blockchain
npm run chain

# Terminal 2: compile and deploy the registry (only when it is not deployed)
cd blockchain
npm run compile
npm run deploy:local

# Back at repository root: re-run discovery/selection only when fresh evidence
# is wanted and SERPAPI_KEY is configured.
python python/main.py select-candidate artifacts/case-001/input.jpg --case case-001

# Anchor exactly the candidate already selected for the case. The command
# hashes its unmodified downloaded bytes and writes anchoring_metadata.json.
python python/main.py anchor --case case-001

# Retrieve the recorded hash and compare it with the preserved artifact.
python python/main.py verify --case case-001
```

The existing case-001 selection has `candidate-001.jpg` as its qualifying
selected artifact.  The command prints its source URL, SHA-256 value,
transaction hash and block number when a new transaction is mined, followed by
the final verification verdict.  If the local node is stopped, not configured,
or the contract has not been deployed, anchoring and retrieval stop with the
actual blockchain error; no transaction data is invented.

For a byte-integrity negative demonstration, copy the preserved artifact,
change any byte, and verify that copy against the case registration:

``` powershell
Copy-Item artifacts/case-001/candidate-001.jpg samples/case-001-tampered.jpg
# Modify the copy with any byte-changing editor, then:
python python/main.py verify --case case-001 --artifact samples/case-001-tampered.jpg
```

### Quality checks

``` powershell
python -m pytest -q
cd blockchain; npm test
```

The Python tests use mocks for network-dependent face selection and do not
depend on SerpApi or a live blockchain. The Hardhat contract tests use their
own in-memory chain.

This order is intentionally incremental. Each phase produces something
testable before the next technology is introduced.
