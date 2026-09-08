# Face Identification & Blockchain Verification

A privacy-conscious evidence verification pipeline that combines **AI-based face similarity**, **reverse image search**, **SHA-256 hashing**, and **blockchain verification**.

The system takes an input image, finds potential matching images from the web, compares faces using **SCRFD + ArcFace**, selects the strongest valid candidate, generates a cryptographic fingerprint using **SHA-256**, and records that fingerprint on an **EVM-compatible blockchain**.

---

## 🚀 Features

- 🧑‍💻 **Face Detection** using SCRFD
- 🧠 **Face Embeddings** using ArcFace / InsightFace
- 🔎 **Reverse Image Search** using Google Lens through SerpApi
- 📊 **Face Similarity Ranking** using cosine similarity
- 📥 **Candidate Image Preservation**
- 🔐 **SHA-256 Cryptographic Hashing**
- ⛓️ **Blockchain Anchoring** using Solidity
- ✅ **On-chain Verification**
- 🌐 **Web-based Frontend**
- 🧪 Automated Python and Hardhat tests
- 📁 Evidence artifacts and metadata preservation

---

## 🏗️ System Architecture

```text
                    ┌──────────────────┐
                    │   User Image     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Face Detection   │
                    │      SCRFD       │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Face Embedding   │
                    │     ArcFace      │
                    └────────┬─────────┘
                             │
                             ▼
                 ┌────────────────────────┐
                 │ Google Lens Search     │
                 │       SerpApi          │
                 └────────────┬───────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │ Candidate Images       │
                 │ Download & Preserve    │
                 └────────────┬───────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │ SCRFD + ArcFace        │
                 │ Candidate Comparison   │
                 └────────────┬───────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │ Similarity Ranking     │
                 │ + Threshold Validation │
                 └────────────┬───────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Selected Image   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    SHA-256       │
                    │  Exact Bytes     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ EVM Blockchain   │
                    │ ContentRegistry  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    VERIFY        │
                    │  HASH MATCH?     │
                    └──────────────────┘
