# Nyaya Architecture & System Design

## 1. High-Level Architecture

```mermaid
graph TD
    A[Client / Frontend / CLI] -->|HTTP POST /api/v1/search| B[FastAPI Backend Router]
    B --> C{Direct Section Intent Detector}
    
    C -->|BNS Query e.g. 'BNS 65(1)'| D[fetch_bns_offence_directly]
    C -->|BNSS Query e.g. 'Section 103'| E[fetch_section_directly]
    C -->|Ambiguous Query| F[BNSS Direct -> BNS Direct Fallback]
    C -->|Semantic Query| G[Hybrid Retrieval Engine]
    
    D --> H[(PostgreSQL: offence_classification)]
    E --> I[(PostgreSQL: statute_chunk)]
    F --> I
    F --> H
    
    G --> J[Dense Search: pgvector cosine distance]
    G --> K[Sparse Search: in-memory BM25Okapi]
    J --> L[Reciprocal Rank Fusion k=60]
    K --> L
    L --> I
```

## 2. Ingestion Pipelines

1. **Statute Chunker (`bns_chunker.py`)**:
   - Parses Pages 1–157 of BNSS 2023.
   - Preserves section atomicity and strict proviso attachment.
   - Populates 788 chunks into `statute_chunk` with BGE-base-en-v1.5 embeddings.

2. **First Schedule Parser (`schedule_parser.py`)**:
   - Parses Pages 158–189 (BNS Offence Classification matrix).
   - Row-boundary streaming parser extracts 474 offence classification rows into `offence_classification`.
   - Extracts `cognizable`, `bailable`, `triable_court` with `needs_review` validation.

## 3. Dual-Table Retrieval Routing

- **Deterministic Routing**: When queries specify an exact section cue (`"what is BNS section 65(1)"` or `"what is section 103 bnss"`), similarity scoring is bypassed and exact rows are fetched deterministically with score 1.0.
- **Ambiguous Fallback**: For queries like `"section 65"`, `statute_chunk` is queried first; if absent, falls back to `offence_classification`.
- **Hybrid RRF**: Semantic questions execute dense cosine + sparse BM25 retrieval fused via Reciprocal Rank Fusion ($k=60$).

