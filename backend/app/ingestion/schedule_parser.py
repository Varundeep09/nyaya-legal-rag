"""
Schedule parser for First Schedule of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023.
Extracts BNS offence classification entries across pages 158-189 into structured records.
"""

import re
from typing import List, Dict, Any, Tuple
from app.core.logging import logger
from app.ingestion.bns_chunker import clean_page_text

DEFAULT_PDF_PATH = "data/raw/bns_bare_act_2023.pdf"
DEFAULT_SOURCE_URI = "data/raw/bns_bare_act_2023.pdf"
SCHEDULE_START_PAGE = 158
SCHEDULE_END_PAGE = 189

# Regex to detect row start beginning with a BNS section number pattern
# e.g., '64(2)', '65(1)', '58 (a)', '111(2)(a)', '103'
ROW_START_RE = re.compile(
    r"^(\d{1,3}(?:\s*\([0-9]+\))?(?:\s*\([a-z0-9]+\))?(?:\s*\([a-z0-9]+\))?)\s+(.*)"
)

# Regex to extract tail metadata from line 1 of a row:
# Captures: 1) Cognizable/Non-cognizable, 2) Bailable/Non-bailable, 3) Triable Court
TAIL_RE = re.compile(
    r"\s+((?:Cognizable|Non-cognizable|According\s+as\s+[^\.]*?cognizable[^\.]*?)\.?)\s+"
    r"((?:Bailable|Non-bailable|According\s+as\s+[^\.]*?bailable[^\.]*?)\.?)\s+"
    r"((?:Court\s+of\s+Session|Magistrate\s+of\s+the\s+first\s+class|Any\s+Magistrate|Court\s+by\s+which[^\.]*?triable|High\s+Court|The\s+court[^\.]*?triable)[^\.]*?\.?)\s*$",
    re.IGNORECASE,
)


def finalize_schedule_row(row_dict: Dict[str, Any], source_uri: str) -> Dict[str, Any]:
    """
    Finalizes a detected row block, attempting best-effort tail extraction from line 1.
    If tail is cleanly extracted, sets cognizable/bailable/triable_court and needs_review=False.
    If tail is ambiguous or wrapped across lines, leaves fields null and flags needs_review=True.
    """
    line1 = row_dict["first_line_rest"]
    m = TAIL_RE.search(line1)

    if m:
        cog = m.group(1).strip().rstrip(".")
        bail = m.group(2).strip().rstrip(".")
        court = m.group(3).strip().rstrip(".")
        needs_review = False
        line1_desc = line1[: m.start()].strip()
        remaining_lines = row_dict["lines"][1:]
        all_desc_lines = ([line1_desc] if line1_desc else []) + remaining_lines
        offence_desc = "\n".join(all_desc_lines).strip()
    else:
        cog = None
        bail = None
        court = None
        needs_review = True
        all_lines = [row_dict["first_line_rest"]] + row_dict["lines"][1:]
        offence_desc = "\n".join(all_lines).strip()

    return {
        "bns_section": row_dict["bns_section"],
        "offence_description": offence_desc,
        "punishment": offence_desc,  # Both stored together as columns are intermixed
        "cognizable": cog,
        "bailable": bail,
        "triable_court": court,
        "needs_review": needs_review,
        "page_number": row_dict["page_number"],
        "source_uri": source_uri,
    }


def parse_first_schedule(
    pages_data: List[Tuple[int, str]], source_uri: str = DEFAULT_SOURCE_URI
) -> List[Dict[str, Any]]:
    """
    Parses the First Schedule across pages 158-189.

    1. Strips running headers and skips page 158 explanatory notes before table columns.
    2. Identifies row boundaries via BNS section number start pattern.
    3. Extracts tail classification fields where cleanly anchored on line 1.

    Returns:
        List of dicts matching the OffenceClassification model schema.
    """
    records = []
    current_row = None
    in_table = False

    for page_num, raw_text in pages_data:
        cleaned = clean_page_text(raw_text)
        for line in cleaned.split("\n"):
            line_s = line.strip()
            if not line_s:
                continue

            # Skip header line '1 2 3 4 5 6'
            if line_s.startswith("1 2 3 4 5 6") or line_s == "1 2 3 4 5 6":
                in_table = True
                continue

            if not in_table:
                continue

            match = ROW_START_RE.match(line_s)
            if match:
                if current_row:
                    records.append(finalize_schedule_row(current_row, source_uri))

                sec_raw = match.group(1)
                sec_norm = re.sub(r"\s+", "", sec_raw)
                line_rest = match.group(2).strip()
                current_row = {
                    "bns_section": sec_norm,
                    "first_line_rest": line_rest,
                    "lines": [line_s],
                    "page_number": page_num,
                }
            else:
                if current_row:
                    current_row["lines"].append(line_s)

    if current_row:
        records.append(finalize_schedule_row(current_row, source_uri))

    logger.info(
        "Parsed %d First Schedule rows across %d pages (%d needs_review=True)",
        len(records),
        len(pages_data),
        sum(1 for r in records if r["needs_review"]),
    )
    return records
