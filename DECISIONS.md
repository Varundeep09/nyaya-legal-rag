# Technical Decisions, Trade-offs & Engineering Log

## 1. Source Corpus Analysis & BNSS vs BNS Discrepancy

### Finding
Inspection of the primary source PDF (`BNS bare act 2023.pdf`) revealed a discrepancy between nominal file naming and literal statutory text:
- **Pages 1–157**: Contain the full text of **The Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)** — the procedural criminal law statute (Act No. 46 of 2023).
- **Pages 158–189**: Contain **The First Schedule** specifying BNS substantive offences, punishments, and triable court classifications.
- **Pages 190–249**: Contain **The Second Schedule** containing 58 statutory forms enacted under BNSS Section 522.

### Decision
In accordance with the specification brief ("Your parser must key off what is actually on the page, not off an assumption about which statute it belongs to"):
- Chunks from Pages 1–157 are stored with metadata `act: "Bharatiya Nagarik Suraksha Sanhita, 2023"` and `act_short: "BNSS"`.
- Schedule rows from Pages 158–189 are stored in `offence_classification` with metadata `act: "Bharatiya Nyaya Sanhita, 2023"` and `act_short: "BNS"`.
- Forms from Pages 190–249 are stored in `data/forms/` with dynamic extracted titles and enabling sections.

---

## 2. Ingestion & Chunking Trade-offs

### Greedy Atom-Packing Strategy
- **Choice**: Implemented an atom-packing chunker (`bns_chunker.py`) that treats each statutory subsection `(1)`, `(2)` as an atomic unit. Provisos (`Provided that...`) and Explanations are attached directly to their parent subsection chunk.
- **Trade-off**: Prevents orphaned proviso chunks that alter legal meaning when retrieved in isolation. Long sections (e.g. Section 35, Section 480) produce chunks up to 1,800 characters, slightly exceeding the 1,200-char soft limit but ensuring 100% legal coherence.

### Chapter False-Positive Bug & Fix
- **Bug**: Page headers printed across page tops (e.g. `"THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023"`) triggered regex false-positives for Chapter titles, causing running header text to pollute chunk metadata.
- **Fix**: Added explicit vertical positional filtering and page-header exclusion regexes to ignore running top headers during PDF parsing.

### Dropped Sections 104 & 105 Bug & Fix
- **Bug**: Regex for section headers (`^\d+\.`) matched inline numbers inside list items `(104)`, causing Sections 104 and 105 to be swallowed into Section 103.
- **Fix**: Refined section header regex to require explicit line starts `^\s*(\d+)\.\s+([A-Z].*)` with uppercase title casing lookahead.

### First Schedule Column Separation
- **Finding**: First Schedule pages (158–189) lack vertical column border lines. PyMuPDF table extraction returned inconsistent column boundaries across multi-line text wraps.
- **Decision**: Implemented a positional streaming row parser (`schedule_parser.py`) that extracts Section, Offence, and Punishment text into unified fields while extracting anchored classification triples (*Cognizable*, *Bailable*, *Triable Court*) when cleanly aligned, flagging complex wrapped rows with `needs_review = true`.

---

## 3. Retrieval, Gating & Model Decisions

### Empirically-Calibrated Refusal Threshold (0.68)
- **Experimentation**: Evaluated dense cosine similarity scores across 12 test queries (6 legal vs 6 off-topic).
- **Result**: Legal queries yielded similarity scores between `0.7027` and `0.7896`. Off-topic queries yielded scores between `0.4970` and `0.6319`.
- **Decision**: Established a strict cutoff threshold of `0.68`. Queries scoring below `0.68` are deterministically refused without invoking LLM generation.
- **Boundary Variance Note**: Near the `0.68` boundary, floating-point precision differences across batch vs single-query CPU inference can cause minor score fluctuations ($\pm 0.005$).

### Citation Accuracy vs Recall Metric Artifact
- **Finding**: In dense-only baseline evaluation, Citation Accuracy scored 100% despite Recall@5 being only 45%.
- **Explanation**: Citation Accuracy measures whether LLM-emitted citations match the context chunks injected into its prompt. When retrieval returns incorrect chunks, the LLM faithfully cites those incorrect chunks, yielding 100% structural citation accuracy despite incorrect retrieval. Evaluation must always pair Citation Accuracy with Recall@5/10 and MRR.

### Gemini API Model Deprecation & Dynamic Failover
- **Quota Challenge**: Google Gemini free-tier limits `gemini-3.6-flash` to 20 requests per day per project, causing 429 quota exhaustion errors during batch evaluation runs.
- **Decision**: Implemented automatic candidate failover in `GeminiProvider` (`app/llm/provider.py`) iterating over `[self.model_name, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]`. If quota limits are reached on the primary model, generation automatically fails over to active lite models without engaging template fallback.

### Binary File Tracking Decision (`data/raw/*.pdf`)
- **Decision**: Tracked primary source PDF `data/raw/bns_bare_act_2023.pdf` in git while untracking generated intermediate PDF forms `data/forms/*.pdf`.
- **Justification**: Ensures GitHub Actions CI runners have instant access to the source bare act PDF required by pytest ingestion tests without external network dependencies.

---

## 4. "With Two More Weeks": Architectural Roadmap

If granted two additional weeks of development, the following improvements would be implemented:
1. **Cross-Encoder Reranking**: Add a lightweight Cross-Encoder model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) to rerank top-20 RRF candidates down to top-5, improving MRR from 0.8592 to >0.92.
2. **Alembic Database Migrations**: Replace `Base.metadata.create_all` with full versioned Alembic migration scripts (`alembic/versions/`).
3. **Intent Classifier for Refusal Boundary**: Replace static 0.68 threshold with a fine-tuned binary intent classifier to resolve ambiguous boundary queries (e.g. tax law vs criminal procedure).
4. **Full Column-Parsed Schedule Table**: Utilize custom OCR / layout-aware vision parsing to achieve 100% column separation across wrapped rows in the First Schedule.
