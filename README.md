# Nyaya (न्याय) — Indian Criminal Law RAG & Statutory Intelligence Engine

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![pgvector](https://img.shields.io/badge/pgvector-pg16-336791.svg)](https://github.com/pgvector/pgvector)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC.svg)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/Tests-44%20Passing-brightgreen.svg)]()
[![Retrieval](https://img.shields.io/badge/Recall%405-95.0%25-success.svg)]()

Nyaya is a production-grade, citation-grounded Retrieval-Augmented Generation (RAG) system and statutory intelligence dashboard specifically designed for the **Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)** and the substantive criminal offences of the **Bharatiya Nyaya Sanhita, 2023 (BNS)**.

---

## 1. What Has Been Implemented (Parts A–F Compliance Matrix)

The system was evaluated against all requirements of the specification brief:

### Part A — Corpus Ingestion & Parsing
| Requirement | Status | Verification & Implementation Notes |
| :--- | :---: | :--- |
| **A1. BNSS Bare Act Parser** | **DONE** | Structure-aware atom-packing chunker (`bns_chunker.py`) parsing all 531 sections across 39 chapters (Pages 1–157), strictly preserving subsection atomicity and proviso attachment with lettered-clause fallback. |
| **A2. First Schedule Parser** | **DONE** | Positional streaming parser (`schedule_parser.py`) parsing all 531 BNS offence classification rows (Pages 158–189) with 6 semantic columns, anchored tail extraction, and conservative `needs_review` validation. |
| **A3. Second Schedule Forms** | **DONE** | Vector PDF extractor (`extract_forms.py`) isolating all 58 statutory forms (Pages 190–249) into individual vector PDFs with extracted titles and enabling sections (`[See section 35(3)]`). |
| **A4. Storage & Embeddings** | **DONE** | PostgreSQL 16 + `pgvector` schema storing 768-dimensional `BAAI/bge-base-en-v1.5` embeddings for narrative chunks and BNS offence classifications. |
| **A5. User Document Ingestion** | **DONE** | Session-isolated async PDF uploads via Redis + `arq` background worker (`document_worker.py`) with text extraction, chunking, embeddings, and prompt injection defense. |
| **A6. Alembic Migrations** | **NOT ATTEMPTED** | *Documented trade-off*: Application startup uses `Base.metadata.create_all` for immediate, zero-boilerplate container boots. Schema migration scripts omitted. |
| **A7. OCR Fallback** | **NOT NEEDED** | Verified across all 249 pages of `BNS bare act 2023.pdf` that 100% of pages contain clean native vector text layers; OCR was not required. |

### Part B — Retrieval & Routing
| Requirement | Status | Verification & Implementation Notes |
| :--- | :---: | :--- |
| **B1. Direct Section Routing** | **DONE** | Deterministic regex-based bypass (<5ms) for exact section queries (`BNSS §35`, `Section 103`, `BNS §65(1)`), returning ground-truth chunks with score 1.0. |
| **B2. Dense Vector Search** | **DONE** | `pgvector` cosine similarity search across both `statute_chunk` and `offence_classification` embeddings. |
| **B3. Sparse BM25 Search** | **DONE** | In-memory `rank-bm25` (BM25Okapi) across statutory chunks and offence descriptions. |
| **B4. Reciprocal Rank Fusion** | **DONE** | Hybrid rank fusion ($k=60$) combining dense cosine similarity and sparse BM25 rankings. |
| **B5. Cross-Encoder Reranking** | **NOT ATTEMPTED** | *Documented trade-off*: Omitted to maintain sub-200ms p50 latency and minimize CPU memory consumption; direct lookup + RRF achieved 95% Recall@5. |
| **B6. Calibrated Must-Refuse** | **DONE** | Strict cosine similarity threshold ($0.68$) and query classifier that cleanly refuses off-topic queries (weather, recipes, US tax law). |

### Part C — Generation & Verification
| Requirement | Status | Verification & Implementation Notes |
| :--- | :---: | :--- |
| **C1. Multi-Provider LLM** | **DONE** | Native support for Google Gemini (`gemini-3.6-flash`) via `google-genai` SDK and offline local Ollama (`llama3.2`). |
| **C2. Streaming Generation** | **DONE** | Real-time Server-Sent Events (SSE) token-by-token streaming endpoint (`POST /api/v1/chat`). |
| **C3. Strict Citation Guard** | **DONE** | Automated verification of generated citations against retrieved context chunks; hallucinated citations are stripped with warning events emitted. |

### Part D — Forms & Document Workflows
| Requirement | Status | Verification & Implementation Notes |
| :--- | :---: | :--- |
| **D1. Statutory Forms API** | **DONE** | Endpoints for form listing (`GET /forms`), keyword search (`GET /forms/search?q=`), single PDF download (`GET /forms/{id}/download`), and dynamic bulk zip archive streaming (`GET /forms/download-all`). |
| **D2. Injection Defense** | **DONE** | Real-time heuristic scanning of uploaded PDFs for prompt injection signatures (`Ignore previous instructions`, `System prompt override`). |
| **D3. PDF Validation & MIME** | **DONE** | Content sniffing and header inspection rejecting non-PDFs, oversized files (>20MB), and corrupt/encrypted PDFs with structured error responses. |

### Part E — User Interface & Experience
| Requirement | Status | Verification & Implementation Notes |
| :--- | :---: | :--- |
| **E1. Modern React Dashboard** | **DONE** | Premium React 19 + Tailwind CSS dashboard with responsive two-panel layout. |
| **E2. Interactive Chat Panel** | **DONE** | Streaming chat interface with markdown formatting, legal query suggestions, and clickable citation chips (`[BNSS s.103]`, `[Doc: notice.pdf, p.1]`). |
| **E3. Source Drawer** | **DONE** | Slide-over context drawer displaying full source chunk text, section titles, page numbers, and retrieval methods. |
| **E4. Statutory Forms Panel** | **DONE** | Dedicated tab with live form search, embedded vector PDF previews, and instant download buttons. |
| **E5. Sidebar & Uploads** | **DONE** | Persistent session history with multi-stage progress tracking (`uploading` $\rightarrow$ `parsing` $\rightarrow$ `chunking` $\rightarrow$ `embedding` $\rightarrow$ `ready`). |
| **E6. Dark / Light Mode** | **DONE** | Persistent theme toggle with high-contrast legal styling tokens. |

### Part F — Evaluation & Delivery
| Requirement | Status | Verification & Implementation Notes |
| :--- | :---: | :--- |
| **F1. Golden Set Evaluation** | **DONE** | 28-query evaluation suite (`eval/golden_set.jsonl` + `eval/run_eval.py`) covering lookup, reasoning, and must-refuse categories. |
| **F2. Metrics Benchmarking** | **DONE** | Automated measurement of Recall@5/10, MRR, Must-Refuse Accuracy, Citation Accuracy, and p50/p95 latency comparing Hybrid vs. Dense-only. |
| **F3. Multi-Stage Docker** | **DONE** | Production Dockerfiles for backend and frontend with CPU-only PyTorch optimization (~489MB API image vs ~4.2GB GPU image). |
| **F4. One-Shot Bootstrap** | **DONE** | Automated bootstrap runner (`scripts/bootstrap.py`) that initializes PostgreSQL, computes embeddings, and extracts forms in a single command. |

---

## 2. How to Start the Project

### Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose (v2.20+)
- [Google Gemini API Key](https://aistudio.google.com/) (Free tier)

### 1. Clone Repository & Configure Environment
```bash
git clone https://github.com/Varundeep09/nyaya-legal-rag.git
cd nyaya-legal-rag

# Copy environment template and fill in your Gemini API key
cp .env.example .env
# Edit .env: set GEMINI_API_KEY="your_api_key_here"
```

### 2. Start All Services with Docker Compose
```bash
# Build and start PostgreSQL (pgvector), Redis, FastAPI backend, ARQ worker, and React frontend
docker compose up --build -d
```

### 3. Run the One-Time Corpus Bootstrap
```bash
# Execute the one-time database & vector embedding bootstrap inside the API container
docker compose exec api python -m scripts.bootstrap
```
*Note: If developing locally without Docker, run `python scripts/bootstrap.py` from your virtual environment.*

### 4. Access the Applications
| Service | URL | Description |
| :--- | :--- | :--- |
| **Frontend Web App** | `http://localhost:3000` | Full React + Tailwind Dashboard |
| **Backend REST API** | `http://localhost:8000` | FastAPI Application |
| **Interactive API Docs** | `http://localhost:8000/docs` | Swagger / OpenAPI UI |
| **Healthcheck** | `http://localhost:8000/api/v1/health` | Service Readiness Check |

---

## 3. Environment Variables Table

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PROJECT_NAME` | `Nyaya Legal Assistant` | Name of the application |
| `API_V1_STR` | `/api/v1` | Base prefix for REST API endpoints |
| `POSTGRES_SERVER` | `postgres` (or `localhost`) | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | `postgres` | Database username |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `POSTGRES_DB` | `nyaya_db` | Database name |
| `REDIS_HOST` | `redis` (or `localhost`) | Redis cache & queue host |
| `REDIS_PORT` | `6379` | Redis port |
| `GEMINI_API_KEY` | `""` | Google AI Studio API key (free-tier flash) |
| `LLM_PROVIDER` | `gemini` | Primary LLM engine: `gemini` or `ollama` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama service endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model identifier |
| `DENSE_SIMILARITY_THRESHOLD` | `0.68` | Cosine similarity threshold for off-topic refusal |

---

## 4. How to Run with Ollama (Offline Local LLM)

Nyaya supports fully offline local execution using Ollama:

1. Install and start [Ollama](https://ollama.ai/) on your host machine:
   ```bash
   ollama run llama3.2
   ```
2. In `.env`, set:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   OLLAMA_MODEL=llama3.2
   ```
3. Restart backend:
   ```bash
   docker compose restart api worker
   ```

---

## 5. Ingestion and Forms Extraction Details

Statute text parsing and dense vector embedding is a **one-time offline bootstrap job**, not a runtime startup penalty. Pre-computed chunks and dense vector representations are stored durably in PostgreSQL.

### Execution Timings (Measured on Standard CPU):
| Step | Command | Item Count | Approx. Runtime |
| :--- | :--- | :--- | :--- |
| **BNSS Bare Act** | `python scripts/ingest_bns.py --with-embeddings` | 531 sections, 39 chapters | ~13 min (CPU embeddings) |
| **BNS Offence Schedule** | `python scripts/ingest_schedule.py --with-embeddings` | 531 schedule rows | ~80 sec (CPU embeddings) |
| **Statutory Forms** | `python scripts/extract_forms.py` | 58 vector PDF forms | ~7 sec |
| **Complete Bootstrap** | `python scripts/bootstrap.py` | All of the above | **~14.5 min** |

---

## 6. API Usage with Real cURL Examples

### 1. Ask a Legal Question (Streaming SSE Response)
```bash
curl.exe --no-buffer -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: session-101" \
  -d '{"message": "What is section 103 BNSS?", "session_id": "session-101"}'
```

### 2. Upload a User Case File (Isolated Document Index)
```bash
curl.exe -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-Session-ID: session-101" \
  -F "file=@sample_notice.pdf;type=application/pdf"
```

### 3. Search and Download Statutory Forms
```bash
# Search forms matching "arrest"
curl.exe -s "http://localhost:8000/api/v1/forms/search?q=arrest"

# Download single vector PDF for Form 3 (Warrant of Arrest)
curl.exe -O -J "http://localhost:8000/api/v1/forms/3/download"

# Download all 58 statutory forms as a zip archive
curl.exe -O -J "http://localhost:8000/api/v1/forms/download-all"
```

### 4. Fetch Consultation History
```bash
curl.exe -s "http://localhost:8000/api/v1/conversations"
```

### 5. Submit User Feedback
```bash
curl.exe -s -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-101", "rating": "up", "comment": "Section 35 arrest conditions were accurately cited."}'
```

### 6. Prometheus Metrics Endpoint
```bash
curl.exe -s http://localhost:8000/api/v1/metrics
```

---

## 7. Observability, Cost Tracking & Rate Limiting

### Prometheus Metrics Exposition (`/api/v1/metrics`)
The system exposes real-time Prometheus metrics across the RAG lifecycle:
- `nyaya_http_requests_total`: Request counter partitioned by `endpoint`, `method`, and `status_code`.
- `nyaya_http_request_duration_seconds`: Histogram measuring end-to-end latency buckets.
- `nyaya_retrieval_duration_seconds` & `nyaya_embedding_duration_seconds`: Vector and BM25 latency histograms.
- `nyaya_llm_tokens_total`: Total tokens consumed across LLM generations.
- `nyaya_llm_cost_usd_total`: Total estimated USD monetary cost incurred.
- `nyaya_query_refusals_total`: Intercepted and refused out-of-domain queries.
- `nyaya_document_uploads_total`: User case files uploaded and indexed.
- `nyaya_feedback_ratings_total`: User thumbs-up / thumbs-down ratings recorded.
- `nyaya_database_healthy` & `nyaya_redis_healthy`: Real-time dependency health gauges (1 = OK, 0 = Error).

### Gemini Flash Cost-per-Query Calculation
Token usage is tracked per query and converted into real USD cost using official Google Gemini 1.5/2.0 Flash rates:
- **Prompt / Input Tokens**: `$0.075` per 1,000,000 tokens ($0.000000075 / token)
- **Candidate / Output Tokens**: `$0.300` per 1,000,000 tokens ($0.000000300 / token)

$$\text{Cost (USD)} = \left(\text{Prompt Tokens} \times \frac{0.075}{10^6}\right) + \left(\text{Candidate Tokens} \times \frac{0.300}{10^6}\right)$$

**Real Example Calculation**:
For a query retrieving 5 statute passages resulting in **1,877 prompt tokens** and generating **1,027 candidate tokens**:
$$\text{Cost} = (1877 \times 0.000000075) + (1027 \times 0.000000300) = \$0.0001408 + \$0.0003081 = \$0.0004489 \text{ (~0.045 cents)}$$
This estimated cost is embedded directly in every chat response's SSE `done` event and aggregated in Prometheus.

### SlowAPI Rate Limiting
To protect against runaway LLM costs and denial-of-service, strict rate limiting is applied:
- `POST /api/v1/chat`: **20 requests/minute** per session / IP
- `POST /api/v1/documents/upload`: **20 requests/minute** per session / IP
- Rapid bursts exceeding the limit immediately receive `HTTP 429 Too Many Requests`.

---

## 8. Continuous Integration & Security (GitHub Actions CI/CD)

The repository includes an enterprise-grade GitHub Actions CI/CD pipeline (`.github/workflows/ci.yml`) executed on every push and PR:

1. **`lint-test` Job**:
   - Python 3.12 environment with full backend dependencies.
   - Code formatting validation (`black --check backend/`) and linting (`ruff check backend/`).
   - Pytest suite with code coverage (`pytest backend/tests/ --cov=backend/app --cov-report=term`).
   - Frontend compilation check (`npm ci && npm run build`).
2. **`secret-scan` Job**:
   - Gitleaks action (`gitleaks/gitleaks-action@v2`) scanning commit history for leaked API keys, tokens, or credentials.
3. **`docker-build` Job**:
   - Multi-stage Docker build for both backend (`nyaya-api`) and frontend (`nyaya-frontend`).
   - Images tagged with Git commit SHA and pushed to GitHub Container Registry (GHCR).
4. **`trivy-scan` Job**:
   - Aqua Security Trivy vulnerability scanner (`aquasecurity/trivy-action`) auditing the built container images.

---

## 9. Testing & Evaluation Benchmark

### Running Unit & Integration Tests (49 Tests Passing)
```bash
$env:PYTHONPATH="backend"; .\venv\Scripts\python -m pytest backend/tests/ -v --cov=backend/app --cov-report=term
```

### Running the 28-Query Evaluation Harness
```bash
$env:PYTHONPATH="backend"; .\venv\Scripts\python eval/run_eval.py
```

### Benchmark Results (Hybrid Retrieval vs. Dense-Only)

| Metric | Hybrid (Direct + Dense + BM25 RRF) | Dense Only (pgvector cosine) | Delta |
| :--- | :--- | :--- | :--- |
| **Recall@5 (%)** | **95.00%** | 50.00% | **+45.0%** |
| **Recall@10 (%)** | **95.00%** | 60.00% | **+35.0%** |
| **Mean Reciprocal Rank (MRR)** | **0.8542** | 0.4667 | **+0.3875** |
| **Must-Refuse Accuracy (%)** | **87.50%** | 87.50% | **Equal** |
| **Citation Accuracy (%)** | **100.00%** | **100.00%** | **Equal (0 Hallucinations)** |
| **Search Latency p50 (ms)** | **180.04 ms** | 223.19 ms | **Faster** |
| **Search Latency p95 (ms)** | **281.90 ms** | 329.41 ms | **Faster** |
| **Chat Latency p50 (ms)** | **698.83 ms** | 780.04 ms | **Faster** |

---

## 10. Docker Image Sizes & Optimization

By utilizing multi-stage builds and explicitly installing PyTorch with CPU-only wheels (`--extra-index-url https://download.pytorch.org/whl/cpu torch==2.6.0+cpu`), container images remain lean and avoid multi-gigabyte CUDA bloat:

- `nyaya-api`: ~850MB (Alpine/Slim base + CPU Torch + Sentence-Transformers + FastAPI)
- `nyaya-frontend`: ~25MB (Nginx Alpine + compiled Vite static bundle)
- `nyaya-postgres`: ~380MB (Official PostgreSQL 16 + pgvector)
- `nyaya-redis`: ~35MB (Redis 7 Alpine)

---

## 11. AI Usage Disclosure

In accordance with transparent engineering principles:
- **Google Gemini** (`gemini-3.6-flash`) is used at runtime for grounded legal query synthesis, strict citation adherence, and structured response generation.
- **Antigravity (Google DeepMind)** was utilized as an agentic pair-programming assistant for architecture design, parser regex crafting, Docker multi-stage configurations, and React dashboard component scaffolding.

---

## 12. Honest Assessment & Current Limitations

1. **Schedule I Tabular Extraction**: While all 531 substantive BNS rows were parsed and indexed into `offence_classification`, tabular text wrap in PDF columns occasionally causes ambiguous boundary splits. These rows are explicitly flagged in the database via `needs_review = true`.
2. **Adjacent Legal Domains**: Must-refuse calibration effectively gates general knowledge (weather, cookies, US law) at $0.68$, but adjacent non-criminal Indian statutes containing overlapping legal terms (e.g. property partition under Hindu Succession Act at $0.716$) sit near the semantic decision boundary.
