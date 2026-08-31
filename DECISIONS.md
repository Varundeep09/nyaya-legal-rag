# Architectural Decisions & Technical Trade-offs

## Date: August 31, 2026

### Critical Finding: Source PDF Corpus Analysis & Act Mismatch Resolution

#### Observation & Analysis
Upon deep inspection of the provided primary corpus PDF (`BNS bare act 2023.pdf`), we identified a fundamental discrepancy between the assignment description and the literal text printed in the source document:
1. **Pages 1–189**: Contain the full text of **THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023** (BNSS 2023 - Act No. 46 of 2023), which consolidates and amends criminal procedure law in India. It does *not* contain the substantive penal provisions of Bharatiya Nyaya Sanhita (BNS 2023).
2. **Pages 158–189 (*The First Schedule*)**: Contain the comprehensive tabular classification of offences (Section, Offence, Punishment, Cognizable/Non-cognizable, Bailable/Non-bailable, Triable Court).
3. **Pages 190–249 (*The Second Schedule*)**: Contain 58 statutory forms (Form No. 1 to Form No. 58) explicitly enacted under section 522 of the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS). For instance, Form No. 1 on page 190 is titled `"NOTICE FOR APPEARANCE BY THE POLICE"` under BNSS section 35(3).

#### Architectural Decision
As required by the specification brief ("Your parser must key off what is actually on the page, not off an assumption about which statute it belongs to"), our system adopts the following principles:
- **Literal Act Metadata Extraction**: Chunks extracted from pages 1–189 are labeled with metadata `act: "Bharatiya Nagarik Suraksha Sanhita, 2023"` and `act_short: "BNSS"`.
- **First Schedule Classification Matrix**: The offence classification schedule (pages 158–189) is parsed as structured relational data and indexed as an explicit citation source (`BNSS Sched-1`).
- **Second Schedule Statutory Forms**: The form extraction pipeline extracts Form 1 through Form 58 from pages 190–249, scraping exact titles printed on the pages (e.g. `FORM-1_NOTICE-FOR-APPEARANCE-BY-THE-POLICE.pdf`), recording `enabling_section` (e.g. `35(3)`), and preserving multi-page form continuity (such as Form No. 33 across pages 222–224).

---

### Database Schema Initialization Trade-off (Direct `create_all` vs Alembic)

#### Decision
For database table creation and pgvector extension enabling during application startup, we utilize `conn.run_sync(Base.metadata.create_all)` inside an async lifespan context manager rather than configuring full Alembic migration scripts (`alembic/versions`).

#### Justification & Trade-off
- **Speed & Simplicity**: In a 4-day hiring technical assignment, setting up Alembic migration scripts adds boilerplate overhead without adding functionality. `Base.metadata.create_all` ensures clean, immediate table creation on a fresh container boot.
- **Production Path**: In a real production deployment post-assignment, schema evolution would be managed via Alembic migration scripts (`alembic revision --autogenerate -m "feat: async db layer"`).

---

### Clause-Boundary Fallback Heuristic & Drafting Style Trade-offs

#### Context & Heuristic Design
In the greedy atom-packing chunker, the atomic unit is the subsection atom. However, when a single subsection atom on its own exceeds the `MAX_CHUNK_SIZE` threshold (1200 chars), the chunker descends to the lettered-clause level `(a), (b), (c)...`. To prevent splitting inside nested conditions (e.g. `(i)`, `(ii)(a)-(e)`) or orphaning provisos, the splitter uses a keyword-based regex heuristic:
`re.compile(r"^\(([a-z])\)\s+(?:against\b|who\b|in\s+whose|for\s+whose)", re.IGNORECASE)`
tuned to the BNSS drafting style for enumerated-persons clauses (such as Section 35).

#### Self-Critique & Observations Across Corpus
Across all 157 narrative pages of BNSS, this fallback path is triggered by **62 distinct sections** (e.g. Sections 35, 187, 246, 479, 480). Spot-checking sections outside Section 35 reveals key architectural tensions:

1. **Where it works well (e.g., Section 480 & Section 187)**:
   - In Section 480 (*When bail may be taken in case of non-bailable offence*), subsection (1) contains two conditions `(i)`, `(ii)` and 4 extensive provisos. All 4 provisos remain strictly attached to subsection (1) in Chunk 1 (1957 chars), preventing any inverted legal meaning upon retrieval.
   - In Section 187 (*Procedure when investigation cannot be completed in 24 hours*), Explanations I & II and both provisos stay tightly glued to Subsection (5) in Chunk 5 (1144 chars).
2. **Where the heuristic shows its limits (e.g., Section 246)**:
   - In Section 246 (*What persons may be charged jointly*), clauses (a) through (g) follow the drafting pattern `(a) persons accused of...`, `(b) persons accused of...`. Because the regex keys specifically on `who / against / in whose / for whose`, it does not split Section 246 into lettered sub-chunks. Consequently, the entire section (2722 chars) is emitted as a single oversized chunk.
   - **Trade-off Evaluation**: While this results in a single chunk exceeding the 1200-char soft limit, it ensures that the critical closing proviso (*"Provided that where a number of persons are charged with separate offences..."*) is 100% attached to all 7 preceding clauses. In a legal retrieval setting, exceeding chunk length by 1.5 KB is far preferable to emitting orphaned 150-char clauses with a detached proviso.
   - **Conclusion**: A keyword heuristic tuned to legislative drafting styles offers high precision against accidental sentence fragmentation, but is inherently coupled to specific grammatical constructs. In a broader multi-statute ingestion system, this would need to transition to dependency-tree grammar parsing or structured legislative XML/markdown schemas.

---

### First Schedule (BNS Offence Classification) Positional Parsing Trade-off

#### Context & Layout Constraints
The First Schedule (pages 158–189) specifies the procedural classification of Bharatiya Nyaya Sanhita (BNS) offences across 6 semantic columns: *1. Section, 2. Offence, 3. Punishment, 4. Cognizable/Non-cognizable, 5. Bailable/Non-bailable, 6. Triable Court*.
However, this is a positional layout table with NO ruled grid lines or table borders. `pdfplumber.extract_tables()` fails completely on these pages, returning empty arrays or corrupt column splits.

#### Engineering Decision & Scope
Rather than attempting brittle x-coordinate slicing across variable column widths that break across line wraps, we implemented a robust row-boundary streaming parser ([`schedule_parser.py`](file:///f:/Dhron%20AI/Assignment/nyaya-legal-rag/backend/app/ingestion/schedule_parser.py)):
1. **Row Detection**: Keys off section number start patterns `^(\d{1,3}(?:\([0-9]+\))?(?:\([a-z]\))?)\s+` at the start of lines following column headers.
2. **Best-Effort Line 1 Tail Extraction**: Inspects the end of line 1 for anchored classification triples (*Cognizable*, *Bailable*, *Triable Court*). When cleanly matched (270 rows), these fields are extracted and stored.
3. **Conservative `needs_review` Flagging**: When classification tail values wrap across multiple lines or contain complex proviso conditions (204 rows, e.g. Section 49 where court text wraps), the parser marks `needs_review = True` and leaves those fields null rather than storing hallucinated or misaligned court names.
4. **Offence Description & Punishment Storage**:
   *Trade-off Statement*: Offence description and punishment text are not reliably separated by column in the unruled stream; both are present in the stored text, used together for citation and verification purposes. We explicitly avoid forcing an unreliable split between columns 2 and 3.

---

### Dual-Table Direct Lookup Routing (BNSS vs BNS)

#### Routing Logic
In [`direct_lookup.py`](file:///f:/Dhron%20AI/Assignment/nyaya-legal-rag/backend/app/retrieval/direct_lookup.py) and [`hybrid_retriever.py`](file:///f:/Dhron%20AI/Assignment/nyaya-legal-rag/backend/app/retrieval/hybrid_retriever.py), `detect_act_and_section_intent()` routes incoming queries across both legal corpora:
- **Explicit BNS queries** (e.g. `"what is BNS section 64(2)"`, `"BNS s.65(1)"`): Deterministically routed to `fetch_bns_offence_directly()` querying `offence_classification`.
- **Explicit BNSS queries** (e.g. `"what is section 103 bnss"`): Deterministically routed to `fetch_section_directly()` querying `statute_chunk`.
- **Ambiguous queries** (e.g. `"section 65"`): Queries `statute_chunk` (BNSS) first; if no match is found, falls back automatically to `offence_classification` (BNS).
