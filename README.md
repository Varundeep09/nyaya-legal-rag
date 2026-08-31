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
TODO

## 8. AI usage disclosure
TODO

## 9. What's incomplete
TODO
