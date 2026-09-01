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

## 1. What Has Been Implemented

1. **Two-Corpus Architecture**:
   - **Primary Corpus (Statutory Law)**: Structure-aware parsing of all 531 sections across 39 chapters of the BNSS 2023 bare act into atomic section/proviso chunks with 768-dimensional `BAAI/bge-base-en-v1.5` embeddings stored in PostgreSQL with `pgvector`.
   - **First Schedule Ingestion**: Ingestion of all 531 BNS offence-classification schedule rows (offence description, punishment, bailable/non-bailable status, triable court, cognizable/non-cognizable status) into a dedicated relational + dense search space.
   - **Second Corpus (User Case Files)**: Session-isolated asynchronous PDF document processing (FIRs, notices, court orders) via an `arq` background worker with Redis queue, PDF text extraction, chunking, embedding, and automatic prompt injection defense scanning.
2. **Deterministic & Hybrid Retrieval Engine**:
   - **Direct Section Routing**: High-precision regex pattern matchers that bypass vector search for unambiguous section queries (`BNSS §35`, `Section 103`, `BNS §65(1)`), returning exact chunks in <5ms.
   - **Reciprocal Rank Fusion (RRF)**: Fusion of dense cosine vector similarity (`pgvector`) and sparse BM25 keyword rankings with constant $k=60$.
   - **Calibrated Must-Refuse Guard**: Strict cosine similarity threshold ($0.68$) and direct query classifier that cleanly refuses off-topic questions (e.g. baking cookies, US tax law, Ohio traffic codes).
3. **Verified LLM Engine & Citation Guard**:
   - Multi-provider support for **Google Gemini** (`gemini-3.6-flash`) and **Ollama** (`llama3.2`).
   - Server-Sent Events (SSE) token-by-token streaming.
   - Strict `CitationGuard` that parses, validates, and automatically strips unverified citations not grounded in retrieved context chunks.
4. **Statutory Forms Repository (Second Schedule)**:
   - Vector extraction and separation of all **58 statutory procedural forms** from pages 190–249 of BNSS 2023 into individual clean single/multi-page PDFs with dynamically extracted titles and enabling sections (`[See section 35(3)]`).
   - Endpoints for real-time form search, individual form download, in-browser PDF preview, and dynamic bulk zip archive generation (`BNSS_Statutory_Forms_1_to_58.zip`).
5. **Modern Two-Panel React Dashboard**:
   - Responsive sidebar with conversation history management and drag-and-drop document upload with real-time progress state tracking (`uploading` $\rightarrow$ `parsing` $\rightarrow$ `chunking` $\rightarrow$ `embedding` $\rightarrow$ `ready`).
   - Interactive chat panel rendering streaming tokens, empty state with 4 example legal queries, copy/stop generation controls, and clickable citation chips (`[BNSS s.103]`, `[BNS s.65(1)]`, `[Doc: notice.pdf, p.1]`).
   - Slide-over **Source Context Drawer** displaying verified legal chunks, page numbers, and retrieval methods.
   - Dedicated **Statutory Forms Panel** with live search, preview modal, and download buttons.
   - Persistent **Dark / Light mode** toggle.
6. **Comprehensive 28-Query Evaluation Harness**:
   - Measures Recall@5, Recall@10, MRR, Citation Accuracy, Refusal Accuracy, and Latency across Hybrid vs. Dense-only retrieval.

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

---

## 7. Testing & Evaluation Benchmark

### Running Unit & Integration Tests (44 Tests)
```bash
$env:PYTHONPATH="backend"; .\venv\Scripts\python -m pytest backend/tests/ -v
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

## 8. Docker Image Sizes & Optimization

By utilizing multi-stage builds and explicitly installing PyTorch with CPU-only wheels (`--extra-index-url https://download.pytorch.org/whl/cpu torch==2.6.0+cpu`), container images remain lean and avoid multi-gigabyte CUDA bloat:

- `nyaya-api`: ~850MB (Alpine/Slim base + CPU Torch + Sentence-Transformers + FastAPI)
- `nyaya-frontend`: ~25MB (Nginx Alpine + compiled Vite static bundle)
- `nyaya-postgres`: ~380MB (Official PostgreSQL 16 + pgvector)
- `nyaya-redis`: ~35MB (Redis 7 Alpine)

---

## 9. AI Usage Disclosure

In accordance with transparent engineering principles:
- **Google Gemini** (`gemini-3.6-flash`) is used at runtime for grounded legal query synthesis, strict citation adherence, and structured response generation.
- **Antigravity (Google DeepMind)** was utilized as an agentic pair-programming assistant for architecture design, parser regex crafting, Docker multi-stage configurations, and React dashboard component scaffolding.

---

## 10. Honest Assessment & Current Limitations

1. **Schedule I Tabular Extraction**: While all 531 substantive BNS rows were parsed and indexed into `offence_classification`, tabular text wrap in PDF columns occasionally causes ambiguous boundary splits. These rows are explicitly flagged in the database via `needs_review = true`.
2. **Adjacent Legal Domains**: Must-refuse calibration effectively gates general knowledge (weather, cookies, US law) at $0.68$, but adjacent non-criminal Indian statutes containing overlapping legal terms (e.g. property partition under Hindu Succession Act at $0.716$) sit near the semantic decision boundary.
