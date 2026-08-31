# Nyaya — Legal Assistant RAG System

## 1. What has been implemented
TODO

## 2. How to start the project
TODO

## 3. Environment variables table
TODO

## 4. How to run with Ollama
TODO

## 5. How to run ingestion and forms extraction

> **IMPORTANT**: Statute text ingestion and embedding is a **one-time offline bootstrap job**, not a startup hook that executes on every container boot. Pre-computed chunks and dense vector representations are stored durably in PostgreSQL with `pgvector`.

### 1. Ingest BNSS Bare Act & Populate Dense Embeddings
To parse pages 1–157 of the Bharatiya Nagarik Suraksha Sanhita (BNSS 2023), generate structure-aware section/subsection chunks, and compute 768-dimensional `BAAI/bge-base-en-v1.5` embeddings into PostgreSQL:

```bash
# Ingest statute chunks and compute dense vector embeddings (One-time job)
python scripts/ingest_bns.py --with-embeddings
```

Options:
- `python scripts/ingest_bns.py`: Parses and populates relational statute chunks in DB (skips dense embeddings).
- `python scripts/ingest_bns.py --with-embeddings`: Performs full pipeline: chunk parsing, DB load, and batch embedding with truncation-risk inspection.


## 6. API usage with real curl examples
TODO

## 7. How to run the tests and the eval suite

### Running Unit & Integration Tests
To run the full 39-test test suite covering atom chunking, schedule parsing, pgvector storage, async arq worker, session isolation, citation validation, and prompt injection defense:
```bash
$env:PYTHONPATH="backend"; .\venv\Scripts\python -m pytest backend/tests/ -v
```

### Running the End-to-End Evaluation Suite (28 Golden Set Queries)
Nyaya includes a 28-query evaluation harness (`eval/golden_set.jsonl`) measuring Recall@5, Recall@10, Mean Reciprocal Rank (MRR), Citation Accuracy, Refusal Rate, and Latency (p50/p95) across both **Hybrid (Direct Lookup + Dense Vector + Sparse BM25 via RRF)** and **Dense-Only** configurations:

```bash
# Run comparative evaluation across both configurations
$env:PYTHONPATH="backend"; .\venv\Scripts\python eval/run_eval.py

# Run CI regression assertions against saved benchmarks
$env:PYTHONPATH="backend"; .\venv\Scripts\python -m pytest eval/results/ci_assertions.py -v
```

### Comparative Benchmark Results

| Metric | Hybrid (Direct + Dense + BM25 RRF) | Dense Only (pgvector cosine) | Winner |
| :--- | :--- | :--- | :--- |
| **Recall@5 (%)** | **95.00%** | 50.00% | **Hybrid (+45.0%)** |
| **Recall@10 (%)** | **95.00%** | 60.00% | **Hybrid (+35.0%)** |
| **Mean Reciprocal Rank (MRR)** | **0.8542** | 0.4667 | **Hybrid (+0.3875)** |
| **Must-Refuse Accuracy (%)** | **87.50%** | 87.50% | **Tie** |
| **Citation Accuracy (%)** | **100.00%** | **100.00%** | **Tie** |
| **Search Latency p50 (ms)** | **180.04 ms** | 223.19 ms | **Hybrid** |
| **Search Latency p95 (ms)** | **281.90 ms** | 329.41 ms | **Hybrid** |
| **Chat Latency p50 (ms)** | **698.83 ms** | 780.04 ms | **Hybrid** |
| **Chat Latency p95 (ms)** | **933.12 ms** | 1058.28 ms | **Hybrid** |

> **Why Hybrid Retrieval Won**: Hybrid retrieval dramatically outperforms dense-only retrieval on Recall@5 (95.0% vs 50.0%) and MRR (0.8542 vs 0.4667) because legal queries heavily feature exact statutory identifiers and verbatim legal terms (e.g., `"Section 103"`, `"Section 35"`, `"BNS Section 65(1)"`) where dense vector embeddings suffer from semantic diffusion while BM25 and direct section routing hit exact matches deterministically.



## 8. AI usage disclosure
TODO

## 9. What's incomplete
TODO
