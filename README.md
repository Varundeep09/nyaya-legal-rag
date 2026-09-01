# Nyaya (न्याय) — Indian Criminal Law RAG & Statutory Intelligence Engine

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![pgvector](https://img.shields.io/badge/pgvector-pg16-336791.svg)](https://github.com/pgvector/pgvector)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC.svg)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/Tests-50%20Passing-brightgreen.svg)]()
[![Retrieval](https://img.shields.io/badge/Recall%405-95.0%25-success.svg)]()

Nyaya is a production-grade, citation-grounded Retrieval-Augmented Generation (RAG) system and statutory intelligence dashboard specifically engineered for the **Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)** and the substantive criminal offences of the **Bharatiya Nyaya Sanhita, 2023 (BNS)**.

---

## 1. What Has Been Implemented (Parts A–F Compliance Matrix)

The system was evaluated against all requirements of the specification brief:

### Part A — Corpus Ingestion & Parsing
| Specific Requirement | Status | Implementation Details & Evidence |
| :--- | :---: | :--- |
| **Structure-Aware Ingestion** | **DONE** | `bns_chunker.py` parses all 531 narrative sections across 39 chapters (Pages 1–157 of `BNS bare act 2023.pdf`). Preserves section atomicity and subsection structure. |
| **Proviso & Explanation Attachment** | **DONE** | Atom-packing algorithm glues `Provided that` and `Explanation` blocks to parent section chunks up to 512 tokens. |
| **First Schedule Offence Parser** | **DONE** | Positional streaming parser (`schedule_parser.py`) extracts 474 BNS offence classification rows (Pages 158–189). |
| **Second Schedule Statutory Forms** | **DONE** | Vector PDF extractor (`extract_forms.py`) isolates all 58 statutory forms (Pages 190–249) into standalone vector PDFs with dynamic title scraping. |
| **Open-Source Embeddings** | **DONE** | `BAAI/bge-base-en-v1.5` (768 dimensions, L2 normalized) with asymmetric prefixes (`passage: ` vs `query: `). |
| **Vector Storage (pgvector)** | **DONE** | PostgreSQL 16 + `pgvector` extension storing 788 narrative statute chunks and 474 offence classification vectors. |
| **Session-Isolated Document Uploads** | **DONE** | PDF upload API (`POST /documents/upload`) with PyMuPDF text extraction, Redis + `arq` worker, and `X-Session-ID` isolation. |
| **Prompt Injection Scanner** | **DONE** | Heuristic scanner detecting prompt override signatures (`Ignore previous instructions`) in uploaded PDFs. |
| **Alembic Database Migrations** | **NOT ATTEMPTED** | *Documented trade-off*: Application lifespan executes `Base.metadata.create_all` for zero-boilerplate container startup. |
| **OCR Fallback Pipeline** | **NOT NEEDED** | Verified across all 249 pages of `BNS bare act 2023.pdf` that 100% of pages contain clean native vector text layers. |

### Part B — Retrieval & Routing
| Specific Requirement | Status | Implementation Details & Evidence |
| :--- | :---: | :--- |
| **Direct Section Routing** | **DONE** | Regex intent detector (`direct_lookup.py`) matching section queries (`BNS s.65(1)`, `BNSS s.103`), returning ground-truth chunks in <5ms with score 1.0. |
| **Dense Vector Search** | **DONE** | `pgvector` cosine similarity search (`<=>` distance operator) over `statute_chunk` and `offence_classification`. |
| **Sparse BM25 Search** | **DONE** | In-memory `rank-bm25` (BM25Okapi) tokenized index over all 1,262 unified statutory chunks. |
| **Reciprocal Rank Fusion (RRF)** | **DONE** | Hybrid rank fusion ($k=60$) combining dense cosine similarity and sparse BM25 rankings. |
| **Metadata Filtering** | **DONE** | Chapter filter (`chapter_filter`) and session ID filtering applied directly in SQL and BM25 post-processing. |
| **Cross-Encoder Reranking** | **NOT ATTEMPTED** | *Documented trade-off*: Omitted to maintain sub-200ms p50 latency and CPU memory bounds; direct lookup + RRF achieved 95.0% Recall@5. |
| **Calibrated Must-Refuse** | **DONE** | Cosine similarity threshold ($0.68$) and explicit non-corpus act gating refusing off-topic queries (weather, recipes, US tax law). |

### Part C — Generation & Verification
| Specific Requirement | Status | Implementation Details & Evidence |
| :--- | :---: | :--- |
| **Multi-Provider LLM** | **DONE** | Support for Google Gemini (`gemini-3.5-flash-lite`, `gemini-3.6-flash`) via `google-genai` SDK and local self-hosted Ollama (`llama3.2`). |
| **SSE Token Streaming** | **DONE** | Asynchronous generator streaming SSE tokens (`POST /api/v1/chat`). |
| **Strict Citation Guard** | **DONE** | Post-generation regex validation (`citation_guard.py`) verifying cited section numbers against retrieved context; hallucinated section numbers stripped. |
| **Model Failover & Proof Metadata** | **DONE** | Automatic candidate failover across Gemini models if quota is hit, capturing real token usage and `finish_reason` proofs. |

### Part D — Forms & Document Workflows
| Specific Requirement | Status | Implementation Details & Evidence |
| :--- | :---: | :--- |
| **Statutory Forms API** | **DONE** | Endpoints for listing (`GET /forms`), search (`GET /forms/search?q=`), single PDF download (`GET /forms/{id}/download`), and bulk ZIP stream (`GET /forms/download-all`). |
| **PDF Validation & Security** | **DONE** | MIME magic byte checking (`%PDF-`), file size limit (20MB), PyMuPDF password/encryption check, and prompt injection scanning. |

### Part E — User Interface & Experience
| Specific Requirement | Status | Implementation Details & Evidence |
| :--- | :---: | :--- |
| **React 19 Dashboard** | **DONE** | Modern two-panel legal dashboard built with React 19 and Tailwind CSS 3.4. |
| **Streaming Chat View** | **DONE** | Markdown formatting, query suggestions, interactive citation chips (`[BNSS s.103]`, `[Doc: notice.pdf, p.1]`). |
| **Source Context Drawer** | **DONE** | Slide-over drawer displaying exact source chunk text, section title, page numbers, and retrieval score. |
| **Statutory Forms View** | **DONE** | Dedicated tab with live form search, embedded vector PDF modal viewer, and instant download buttons. |
| **Dark / Light Mode** | **DONE** | Persistent dark/light theme switching with custom legal design tokens. |

### Part F — Evaluation & Infrastructure
| Specific Requirement | Status | Implementation Details & Evidence |
| :--- | :---: | :--- |
| **Golden Set Evaluation** | **DONE** | 30-query evaluation harness (`eval/golden_set.jsonl` + `eval/run_eval.py`) covering lookup, reasoning, refusal, and citation validity. |
| **Metrics Benchmarking** | **DONE** | Measurement of Recall@5 (95%), Recall@10 (100%), MRR (0.8592), Must-Refuse Accuracy (100%), and latency p50 (184ms) comparing 3 baselines. |
| **CI Regression Assertions** | **DONE** | Pytest assertions (`eval/results/ci_assertions.py`) enforcing metric performance floors on every build. |
| **Multi-Stage Dockerfiles** | **DONE** | Multi-stage Dockerfiles for backend (CPU-only PyTorch optimization, ~489MB) and frontend (Nginx Alpine static build, ~26MB). |
| **Docker Compose Services** | **DONE** | `docker-compose.yml` orchestrating PostgreSQL 16 (pgvector), Redis 7, FastAPI API, ARQ Worker, and React Frontend. |
| **GitHub Actions Pipeline** | **DONE** | 4-job CI workflow (`.github/workflows/ci.yml`) running Black, Ruff, Pytest with coverage, Gitleaks secret scanning, Docker build & push to GHCR, direct Trivy CLI scanning, and SARIF upload. |

---

## 2. How to Start the Project

### Prerequisites
- **Docker Desktop** (v24.0+) with **Docker Compose** (v2.20+)
- **WSL2** (Windows Subsystem for Linux 2) if running on Windows
- **Google Gemini API Key** (Free-tier from [Google AI Studio](https://aistudio.google.com/))

### Step-by-Step Instructions

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Varundeep09/nyaya-legal-rag.git
   cd nyaya-legal-rag
   ```

2. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set your Google Gemini API key:
   ```env
   GEMINI_API_KEY="your_actual_gemini_api_key_here"
   ```

3. **Start All Services with Docker Compose**:
   ```bash
   docker compose up --build -d
   ```
   > **IMPORTANT**: `docker compose up -d` starts **BOTH** the frontend and backend containers together (along with PostgreSQL, Redis, and ARQ Worker) in a single command.

4. **Run the One-Time Corpus Bootstrap Command**:
   ```bash
   docker compose exec api python -m scripts.bootstrap
   ```
   > **IMPORTANT**: The bootstrap command is a **SEPARATE one-time command** that must be executed after containers become healthy. It initializes database tables, parses the BNS/BNSS statutory PDFs, populates 788 narrative section embeddings + 474 offence classification embeddings, and extracts 58 statutory forms before the chat/forms features have data.

5. **Access Application Endpoints**:
   - **Frontend Web App**: [`http://localhost:3000`](http://localhost:3000) (React 19 Legal Dashboard)
   - **Backend REST API**: [`http://localhost:8000`](http://localhost:8000) (FastAPI Server)
   - **Interactive OpenAPI Documentation**: [`http://localhost:8000/docs`](http://localhost:8000/docs) (Swagger UI)
   - **Prometheus Metrics**: [`http://localhost:8000/api/v1/metrics`](http://localhost:8000/api/v1/metrics)

---

## 3. Environment Variables Table

| Variable | Safe Default | Description |
| :--- | :--- | :--- |
| `PROJECT_NAME` | `Nyaya Legal Assistant` | Application name displayed in headers and logs. |
| `API_V1_STR` | `/api/v1` | URL prefix for all REST API endpoints. |
| `POSTGRES_SERVER` | `postgres` (or `localhost`) | PostgreSQL hostname inside Docker network. |
| `POSTGRES_PORT` | `5432` | PostgreSQL port number. |
| `POSTGRES_USER` | `postgres` | Database username. |
| `POSTGRES_PASSWORD` | `postgres` | Database password. |
| `POSTGRES_DB` | `nyaya_db` | Main database name. |
| `REDIS_HOST` | `redis` (or `localhost`) | Redis host for rate limiting and background queues. |
| `REDIS_PORT` | `6379` | Redis port number. |
| `GEMINI_API_KEY` | `""` | Google AI Studio API key for Gemini generation. |
| `LLM_PROVIDER` | `gemini` | Text generation provider: `gemini` or `ollama`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint for local self-hosted Ollama instance. |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model identifier. |
| `DENSE_SIMILARITY_THRESHOLD` | `0.68` | Cosine similarity threshold for off-topic query refusal. |

---

## 4. How to Run with Ollama (Offline Local LLM)

Nyaya's LLM abstraction layer includes a dedicated provider implementation (`OllamaProvider` in `backend/app/llm/provider.py`) using `httpx` asynchronous HTTP streaming against Ollama's native `/api/generate` endpoint:

1. **Install and Run Ollama on host machine**:
   ```bash
   ollama run llama3.2
   ```
2. **Configure `.env`**:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   OLLAMA_MODEL=llama3.2
   ```
3. **Restart API container**:
   ```bash
   docker compose restart api worker
   ```

---

## 5. How to Run Ingestion & Forms Extraction

Statute parsing and vector embedding are executed via one-time bootstrap commands.

### Measured Execution Timings (Standard CPU):
| Task | Command | Yield | Runtime |
| :--- | :--- | :--- | :--- |
| **BNSS Narrative Act** | `python -m scripts.ingest_bns --with-embeddings` | 531 sections, 39 chapters | ~13 minutes |
| **BNS Offence Schedule** | `python -m scripts.ingest_schedule --with-embeddings` | 474 classification rows | ~90 seconds |
| **Statutory Forms** | `python -m scripts.extract_forms` | 58 vector PDF forms | ~10 seconds |
| **Unified Bootstrap** | `python -m scripts.bootstrap` | Full corpus initialization | **~14.5 minutes** |

---

## 6. API Usage with Real cURL Examples

### 1. Chat Endpoint (SSE Streaming Response)
```bash
curl.exe --no-buffer -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-session-101" \
  -d '{"message": "What is section 35 BNSS?"}'
```

### 2. Search Endpoint (Hybrid Vector & Direct Search)
```bash
curl.exe -s -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "arrest without warrant", "top_k": 5}'
```

### 3. User Document Upload Endpoint
```bash
curl.exe -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-Session-ID: test-session-101" \
  -F "file=@sample_notice.pdf;type=application/pdf"
```

### 4. Statutory Forms Endpoints
```bash
# Search statutory forms
curl.exe -s "http://localhost:8000/api/v1/forms/search?q=arrest"

# Download Form 3 (Warrant of Arrest) vector PDF
curl.exe -O -J "http://localhost:8000/api/v1/forms/3/download"

# Bulk download all 58 statutory forms as ZIP archive
curl.exe -O -J "http://localhost:8000/api/v1/forms/download-all"
```

### 5. Submit User Feedback
```bash
curl.exe -s -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-session-101", "rating": "up", "comment": "Accurate statutory citations."}'
```

### 6. Prometheus Metrics Endpoint
```bash
curl.exe -s http://localhost:8000/api/v1/metrics
```

### 7. Health Check Endpoint
```bash
curl.exe -s http://localhost:8000/api/v1/health
```

---

## 7. How to Run Tests & Evaluation Suite

### Running the Full Pytest Suite (50 Tests Passing)
```bash
$env:PYTHONPATH="backend"; .\venv\Scripts\python -m pytest backend/tests/ -v --cov=backend/app --cov-report=term
```

### Running the Evaluation Benchmark Harness
```bash
$env:PYTHONPATH="backend"; .\venv\Scripts\python eval/run_eval.py
```

### Real Benchmark Results (Hybrid RRF vs. Baselines)

| Metric | Hybrid RRF (Production) | Dense Only (pgvector) | BM25 Only |
| :--- | :---: | :---: | :---: |
| **Recall@5 (%)** | **95.00%** | 45.00% | 60.00% |
| **Recall@10 (%)** | **100.00%** | 55.00% | 75.00% |
| **Mean Reciprocal Rank (MRR)** | **0.8592** | 0.4167 | 0.4729 |
| **Must-Refuse Accuracy (%)** | **100.00%** | 100.00% | 37.50% |
| **Citation Format Validity (%)** | **100.00%** | 100.00% | N/A |
| **Citation Identity Validity (%)** | **100.00%** | 100.00% | N/A |
| **Search Latency p50 (ms)** | **184.19 ms** | 187.17 ms | 84.90 ms |

---

## 8. AI Usage Disclosure

In accordance with transparent engineering principles:

- **AI Tools Used**: 
  - **Gemini / Antigravity IDE**: Implementation, chunker regex crafting, Docker multi-stage configurations, React dashboard scaffolding.
  - **Claude (Anthropic)**: Prompt architecture design, evaluation harness review, and verification orchestration.
- **Representative Prompts Used**:
  1. *"Design a structure-aware chunker for Indian statutory bare acts that keeps section sub-clauses atomic and glues provisos to parent section headers."*
  2. *"Create a positional streaming parser for unruled PDF table pages of the BNS First Schedule offence matrix."*
  3. *"Write a Reciprocal Rank Fusion algorithm combining pgvector cosine similarity and rank-bm25 scores."*
  4. *"Implement a post-generation citation guard that validates extracted section numbers against retrieved context chunks."*
  5. *"Configure a 4-job GitHub Actions CI workflow running pytest, black, ruff, gitleaks, docker build, and trivy CLI vulnerability scanning."*
- **Prompt Refinement Example (Section 104/105 Swallowing Bug)**:
  - *Initial Attempt*: Section header regex `^\d+\.` matched numbers inside sub-clause lists `(104)`, causing Sections 104 and 105 to be swallowed into Section 103.
  - *Refinement*: Updated line-start regex to require explicit line boundary `^\s*(\d+)\.\s+([A-Z].*)` combined with a forward lookahead requiring section title casing.
- **Manual Engineering & Debugging**:
  - Fixed chunk fragmentation where long definitions (BNSS Section 2) exceeded model token limits (512 tokens).
  - Fixed chapter false-positive matches on running header text across PDF page tops.
  - Handled Google Gemini free-tier daily quota limits by implementing automatic candidate model failover (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`).

---

## 9. What's Incomplete & Current Limitations

1. **GitHub-Hosted CI Runners**: Using GitHub-hosted Ubuntu runners (`ubuntu-latest`) rather than a self-hosted runner infrastructure.
2. **First Schedule Positional Column Parsing**: ~43% of First Schedule rows have complex multi-line text wrapping in column 6 (Triable Court), triggering conservative `needs_review = true` flags while preserving full row text for citation search.
3. **Citation Guard Scope**: Validates section-level citation presence (`[BNSS s.35]`), but does not validate lettered sub-clause labels (`(c)`) within a single section chunk.
4. **Database Schema Migrations**: Uses `Base.metadata.create_all` during application lifespan rather than explicit Alembic migration scripts.
5. **Cross-Encoder Reranking**: Omitted cross-encoder reranking stage to preserve sub-200ms p50 search latency and lower memory bounds on CPU hardware.
6. **Container Image Sizes**:
   - Backend API (`nyaya-api`): **~489 MB** (CPU-only PyTorch build).
   - Frontend (`nyaya-frontend`): **~26 MB** (Nginx Alpine + Vite build).
