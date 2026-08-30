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
