"""
Structure-aware legal parser and chunker for narrative BNSS text (pages 1-157).
Implements greedy atom-packing to ensure section atomicity, preserving provisos,
explanations, and illustrations attached to their parent clauses.
Features chapter heading false-positive guards and two-tier clause splitting.
"""

import re
from typing import List, Dict, Any, Tuple, Optional, Set
import pdfplumber

# Maximum character threshold for a single chunk before splitting
MAX_CHUNK_SIZE = 1200

# Constants for statute metadata
ACT_NAME = "Bharatiya Nagarik Suraksha Sanhita, 2023"
ACT_SHORT = "BNSS"
DEFAULT_SOURCE_URI = "data/raw/bns_bare_act_2023.pdf"

# Words that indicate a line is referring to a section rather than defining one
NON_SECTION_PREFIXES = {
    "section",
    "sections",
    "under",
    "of",
    "in",
    "by",
    "or",
    "and",
    "to",
    "see",
    "sub-section",
    "sub-sections",
    "pursuant to",
    "refers to",
    "with",
}


def _looks_like_real_chapter_title(text: str) -> bool:
    """
    Checks if chapter title candidate is ALL-CAPS (ignoring punctuation/digits/whitespace).
    Empty text is considered valid (next-line lookahead will resolve title).
    """
    letters_only = re.sub(r"[^A-Za-z]", "", text)
    return letters_only.isupper() if letters_only else True


def clean_chapter_title_line(text: str) -> str:
    """
    Strips trailing lowercase/mixed-case margin notes that might appear on the
    same line as an uppercase chapter title (e.g. 'THE JUDGMENT themselves.' -> 'THE JUDGMENT').
    """
    if not text:
        return ""
    words = text.strip().split()
    upper_words = []
    for w in words:
        clean_w = re.sub(r"[^A-Za-z]", "", w)
        if clean_w and clean_w.isupper():
            upper_words.append(w)
        else:
            break
    if upper_words:
        return " ".join(upper_words)
    return text.strip()


def fix_chapter_title_artifact(title: str) -> str:
    """
    Fixes PDF-extraction artifact where a stray space is inserted after the
    first letter of the first word in a chapter title.
    E.g., 'C ONSTITUTION OF CRIMINAL COURTS AND OFFICES' -> 'CONSTITUTION OF CRIMINAL COURTS AND OFFICES'
          'P OWER OF COURTS' -> 'POWER OF COURTS'
          'J URISDICTION OF THE...' -> 'JURISDICTION OF THE...'
    Does NOT mangle clean titles like 'ARREST OF PERSONS'.
    """
    if not title:
        return ""
    title = title.strip()
    return re.sub(r"^([A-Z])\s([A-Z]{2,})", r"\1\2", title)


def clean_page_text(text: str) -> str:
    """
    Cleans raw page text from PDF:
    - Strips bare page-number headers/footers
    - Strips Gazette header noise (e.g. THE GAZETTE OF INDIA EXTRAORDINARY, Part II, etc.)
    - Dehyphenates words broken across line breaks
    - Preserves section and paragraph breaks
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    for i, line in enumerate(lines):
        line_str = line.strip()

        # Strip top or bottom bare page number lines (e.g. "155" or "2")
        if (i < 3 or i >= len(lines) - 2) and re.match(r"^\d{1,3}$", line_str):
            continue

        # Strip Gazette running header/footer noise lines
        if any(
            noise in line_str
            for noise in [
                "THE GAZETTE OF INDIA EXTRAORDINARY",
                "REGISTERED NO.",
                "MINISTRY OF LAW AND JUSTICE",
                "PUBLISHED BY AUTHORITY",
                "Separate paging is given",
                "EXTRAORDINARY",
                "[Part II—",
                "[Part II-",
                "Sec. 1]",
                "PART II—Section 1",
                "PART II-Section 1",
            ]
        ):
            continue

        # Strip separator lines (__________)
        if re.match(r"^_{4,}$", line_str):
            continue

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)

    # Dehyphenate words split across line breaks (e.g. "investi-\ngation" -> "investigation")
    cleaned_text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", cleaned_text)

    return cleaned_text


def extract_pages(
    pdf_path: str, start_page: int = 1, end_page: int = 157
) -> List[Tuple[int, str]]:
    """
    Extracts raw text per page from PDF between start_page and end_page (1-indexed, inclusive).
    Returns list of tuples: (page_number, raw_text).
    """
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        actual_end = min(end_page, total_pages)
        for idx in range(start_page - 1, actual_end):
            page_num = idx + 1
            raw_text = pdf.pages[idx].extract_text() or ""
            pages_text.append((page_num, raw_text))
    return pages_text


def extract_cross_references(text: str) -> List[str]:
    """
    Detects legal cross-references in text after line-rejoining & dehyphenation.
    E.g. 'section 2', 'section 35(3)', 'sections 103 to 105', 'sub-section (1) of section 187'.
    """
    if not text:
        return []

    pattern = re.compile(
        r"\b(?:sections?|sub-section)\s+\d+(?:\(\d+\))?(?:\([a-z]\))?(?:\s*(?:to|and|,)\s*\d+(?:\(\d+\))?)?",
        re.IGNORECASE,
    )

    matches = []
    for match in pattern.finditer(text):
        ref = match.group(0).strip()
        if ref and ref not in matches:
            matches.append(ref)
    return matches


def split_section_into_subsections(section_text: str) -> List[str]:
    """
    Splits section text into subsection atoms: (1), (2), (3)...
    Provisos, Explanations, and Illustrations are glued to the preceding atom.
    """
    lines = section_text.split("\n")
    atoms = []
    current_atom_lines = []

    # Numbered subsection start: e.g. "(1)", "(2)", or "35. (1)" at line start
    subsec_re = re.compile(r"^(?:\d+\.\s*)?\((\d+)\)\s*")

    for line in lines:
        line_s = line.strip()
        m = subsec_re.match(line_s)
        # If line starts a new numbered subsection (and it's not the very first line of atom 0)
        if (
            m
            and current_atom_lines
            and (not current_atom_lines[0].strip().startswith(line_s[:4]))
        ):
            atoms.append("\n".join(current_atom_lines).strip())
            current_atom_lines = [line]
        else:
            current_atom_lines.append(line)

    if current_atom_lines:
        atoms.append("\n".join(current_atom_lines).strip())

    return [a for a in atoms if a]


def split_atom_into_clauses(atom_text: str) -> List[str]:
    """
    Tier-1 splitting: Splits an oversized subsection atom into top-level lettered clause atoms (a), (b), (c)...
    matching keyword-based heuristic (who, against, in whose, for whose).
    Provisos, Explanations, Illustrations, and nested sub-items (i),(ii) stay glued
    to the clause they belong to.
    """
    lines = atom_text.split("\n")
    clause_atoms = []
    current_clause_lines = []

    top_clause_re = re.compile(
        r"^\(([a-z])\)\s+(?:against\b|who\b|in\s+whose|for\s+whose)", re.IGNORECASE
    )
    proviso_or_expl = re.compile(
        r"^(?:Provided|Explanation|Illustration|Exception)", re.IGNORECASE
    )

    for line in lines:
        line_s = line.strip()
        m = top_clause_re.match(line_s)
        is_proviso = proviso_or_expl.match(line_s)

        if m and not is_proviso and current_clause_lines:
            clause_atoms.append("\n".join(current_clause_lines).strip())
            current_clause_lines = [line]
        else:
            current_clause_lines.append(line)

    if current_clause_lines:
        clause_atoms.append("\n".join(current_clause_lines).strip())

    return [c for c in clause_atoms if c]


def split_atom_tier2_generic_clauses(atom_text: str) -> List[str]:
    """
    Tier-2 generic splitting: For atoms/clauses that still exceed MAX_CHUNK_SIZE (such as Section 2 Definitions),
    splits on ANY generic lettered clause header (a), (b), (c)... while preserving provisos and explanations.
    """
    lines = atom_text.split("\n")
    clause_atoms = []
    current_clause_lines = []

    generic_clause_re = re.compile(r"^\(([a-z]{1,2})\)\s+", re.IGNORECASE)
    proviso_or_expl = re.compile(
        r"^(?:Provided|Explanation|Illustration|Exception)", re.IGNORECASE
    )

    for line in lines:
        line_s = line.strip()
        m = generic_clause_re.match(line_s)
        is_proviso = proviso_or_expl.match(line_s)

        if m and not is_proviso and current_clause_lines:
            clause_atoms.append("\n".join(current_clause_lines).strip())
            current_clause_lines = [line]
        else:
            current_clause_lines.append(line)

    if current_clause_lines:
        clause_atoms.append("\n".join(current_clause_lines).strip())

    return [c for c in clause_atoms if c]


def pack_atom_clauses_greedily(
    clauses: List[str], max_size: int = MAX_CHUNK_SIZE
) -> List[str]:
    """
    Greedily packs a list of clause atoms into chunks up to max_size.
    Absorbs short introductory preambles to prevent orphaning context.
    """
    chunks = []
    current_buffer = []
    current_len = 0

    for clause in clauses:
        c_len = len(clause)
        proj_len = current_len + (2 if current_buffer else 0) + c_len
        if proj_len > max_size and current_buffer:
            if current_len < 350 and c_len > max_size:
                current_buffer.append(clause)
                chunks.append("\n\n".join(current_buffer).strip())
                current_buffer = []
                current_len = 0
            else:
                chunks.append("\n\n".join(current_buffer).strip())
                current_buffer = [clause]
                current_len = c_len
        else:
            current_buffer.append(clause)
            current_len = proj_len

    if current_buffer:
        chunks.append("\n\n".join(current_buffer).strip())

    return chunks


def pack_atoms_greedily(
    atoms: List[str],
    max_size: int = MAX_CHUNK_SIZE,
    fallback_tracker: Optional[Set[str]] = None,
    sec_num: Optional[str] = None,
) -> List[str]:
    """
    Greedily packs atoms into chunks without exceeding max_size.
    Uses two-tier clause fallback (Tier 1: keyword-gated, Tier 2: generic clause)
    if a single atom exceeds max_size.
    """
    chunks = []
    current_buffer = []
    current_len = 0

    for atom in atoms:
        atom_len = len(atom)

        # If single atom is oversized (> max_size)
        if atom_len > max_size:
            if fallback_tracker is not None and sec_num is not None:
                fallback_tracker.add(sec_num)

            # Tier 1: keyword-gated splitting
            clauses = split_atom_into_clauses(atom)

            # Tier 2: if Tier 1 keyword heuristic produced <= 1 clause (e.g. Section 2 Definitions, Section 246)
            if len(clauses) <= 1:
                tier2_clauses = split_atom_tier2_generic_clauses(atom)
                if len(tier2_clauses) > 1:
                    clauses = tier2_clauses

            if len(clauses) > 1:
                packed_sub = pack_atom_clauses_greedily(clauses, max_size=max_size)
                for sub_chunk in packed_sub:
                    if current_buffer:
                        chunks.append("\n\n".join(current_buffer).strip())
                        current_buffer = []
                        current_len = 0
                    chunks.append(sub_chunk)
            else:
                if current_buffer:
                    chunks.append("\n\n".join(current_buffer).strip())
                    current_buffer = []
                    current_len = 0
                chunks.append(atom)
            continue

        # Check if adding atom exceeds max_size
        projected_len = current_len + (2 if current_buffer else 0) + atom_len
        if projected_len > max_size and current_buffer:
            chunks.append("\n\n".join(current_buffer).strip())
            current_buffer = [atom]
            current_len = atom_len
        else:
            current_buffer.append(atom)
            current_len = projected_len

    if current_buffer:
        chunks.append("\n\n".join(current_buffer).strip())

    return chunks


def parse_chapters_and_sections(
    pages_text: List[Tuple[int, str]],
    source_uri: str = DEFAULT_SOURCE_URI,
    stats: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Walks cleaned text of pages 1-157 and yields structured StatuteChunk dictionaries
    using greedy atom-packing. Tracks fallback section metrics if stats dict is provided.
    Includes strict uppercase chapter heading guard to prevent false-positive corruption.
    """
    doc_lines: List[Tuple[int, str]] = []

    for page_num, raw_text in pages_text:
        cleaned = clean_page_text(raw_text)
        for line in cleaned.split("\n"):
            doc_lines.append((page_num, line))

    chapter_header_re = re.compile(r"^CHAPTER\s+([IVXLCDM]+)\b\s*(.*)", re.IGNORECASE)
    section_start_re = re.compile(r"^(.*?)\b(\d{1,3})\.\s*(.*)")

    CROSS_REF_TRIGGER_WORDS = {
        "section",
        "sections",
        "sub-section",
        "sub-sections",
        "clause",
        "clauses",
    }

    section_blocks: List[Dict[str, Any]] = []
    current_block: Optional[Dict[str, Any]] = None
    current_chapter: Optional[str] = None
    current_chapter_title: Optional[str] = None
    running_max_sec: int = 0

    idx = 0
    while idx < len(doc_lines):
        page_num, line = doc_lines[idx]
        line_trimmed = line.strip()

        # Check for Chapter Header with False-Positive Guard
        chap_match = chapter_header_re.match(line_trimmed)
        if chap_match:
            raw_num = chap_match.group(1).upper()
            raw_title = chap_match.group(2).strip()
            cleaned_raw = clean_chapter_title_line(raw_title)

            candidate_title = cleaned_raw
            advanced_lines = 0

            # If same-line title is empty or not ALL-CAPS, lookahead to next line
            if not candidate_title or not _looks_like_real_chapter_title(
                candidate_title
            ):
                if idx + 1 < len(doc_lines):
                    next_page, next_line = doc_lines[idx + 1]
                    cleaned_next = clean_chapter_title_line(next_line.strip())
                    if (
                        cleaned_next
                        and _looks_like_real_chapter_title(cleaned_next)
                        and not cleaned_next.upper().startswith("CHAPTER")
                    ):
                        candidate_title = cleaned_next
                        advanced_lines = 1

            # Only accept as chapter header if candidate_title is real ALL-CAPS title
            if candidate_title and _looks_like_real_chapter_title(candidate_title):
                current_chapter = raw_num
                current_chapter_title = fix_chapter_title_artifact(candidate_title)
                idx += 1 + advanced_lines
                continue
            # Otherwise: false positive! Do not consume, treat line as ordinary text below

        # Check for Section Start
        sec_match = section_start_re.match(line_trimmed)
        if sec_match:
            prefix = sec_match.group(1).strip()
            sec_num_str = sec_match.group(2)
            body_start = sec_match.group(3).strip()

            sec_val = int(sec_num_str)
            if 1 <= sec_val <= 531:
                prefix_words = set(re.findall(r"[a-zA-Z\-]+", prefix.lower()))

                is_cross_ref_word = bool(
                    prefix_words.intersection(CROSS_REF_TRIGGER_WORDS)
                )
                is_backward_jump = sec_val <= running_max_sec
                is_too_far_forward = (
                    running_max_sec > 0 and sec_val > running_max_sec + 5
                )

                accept = False
                if not is_cross_ref_word and len(prefix) < 60:
                    if not prefix:  # clean line start
                        accept = (sec_val > running_max_sec) and (
                            sec_val <= running_max_sec + 10 or running_max_sec == 0
                        )
                    else:
                        accept = not is_backward_jump and not is_too_far_forward

                if accept:
                    running_max_sec = sec_val
                    sec_title = (
                        prefix
                        if (prefix and not prefix.endswith("."))
                        else f"Section {sec_num_str}"
                    )
                    if prefix.endswith("."):
                        sec_title = prefix[:-1]

                    if current_block:
                        section_blocks.append(current_block)

                    line_content = (
                        f"{sec_num_str}. {body_start}"
                        if body_start
                        else f"{sec_num_str}."
                    )
                    current_block = {
                        "act": ACT_NAME,
                        "act_short": ACT_SHORT,
                        "chapter": current_chapter,
                        "chapter_title": current_chapter_title,
                        "section_number": sec_num_str,
                        "section_title": sec_title,
                        "lines": [(page_num, line_content)],
                        "page_start": page_num,
                        "page_end": page_num,
                        "needs_review": False,
                    }
                    idx += 1
                    continue

        if current_block:
            current_block["lines"].append((page_num, line))
            current_block["page_end"] = page_num

        idx += 1

    if current_block:
        section_blocks.append(current_block)

    chunks: List[Dict[str, Any]] = []
    global_section_seq: Dict[str, int] = {}
    fallback_sections: Set[str] = set()

    for block in section_blocks:
        sec_num = block["section_number"]
        block_lines = block["lines"]
        page_start = block["page_start"]
        page_end = block["page_end"]

        full_block_text = "\n".join([ln[1] for ln in block_lines]).strip()
        full_block_text = re.sub(r"\n{3,}", "\n\n", full_block_text)

        # If total section text <= MAX_CHUNK_SIZE (1200 chars), emit ONE chunk
        if len(full_block_text) <= MAX_CHUNK_SIZE:
            seq = global_section_seq.get(sec_num, 0) + 1
            global_section_seq[sec_num] = seq
            chunk_id = f"bnss-s{sec_num}-{seq:03d}"

            sub_match = re.search(r"^\d+\.\s*(\(\d+\))", full_block_text)
            subsection = sub_match.group(1) if sub_match else None

            chunks.append(
                {
                    "act": block["act"],
                    "act_short": block["act_short"],
                    "chapter": block["chapter"],
                    "chapter_title": block["chapter_title"],
                    "section_number": sec_num,
                    "section_title": block["section_title"],
                    "subsection": subsection,
                    "clause": None,
                    "text": full_block_text,
                    "has_illustration": "Illustration" in full_block_text,
                    "has_proviso": any(
                        p in full_block_text
                        for p in [
                            "Provided that",
                            "Provided further that",
                            "Provided also that",
                        ]
                    ),
                    "has_exception": "Exception" in full_block_text,
                    "page_start": page_start,
                    "page_end": page_end,
                    "chunk_id": chunk_id,
                    "source_uri": source_uri,
                    "references_json": extract_cross_references(full_block_text),
                    "needs_review": False,
                }
            )
        else:
            # Parse into subsection atoms and pack greedily
            subsecs = split_section_into_subsections(full_block_text)
            packed_texts = pack_atoms_greedily(
                subsecs,
                max_size=MAX_CHUNK_SIZE,
                fallback_tracker=fallback_sections,
                sec_num=sec_num,
            )

            for p_text in packed_texts:
                seq = global_section_seq.get(sec_num, 0) + 1
                global_section_seq[sec_num] = seq
                chunk_id = f"bnss-s{sec_num}-{seq:03d}"

                sub_match = re.search(r"^(\(\d+\)|\([a-z]\))", p_text.strip())
                subsection = sub_match.group(1) if sub_match else None

                chunks.append(
                    {
                        "act": block["act"],
                        "act_short": block["act_short"],
                        "chapter": block["chapter"],
                        "chapter_title": block["chapter_title"],
                        "section_number": sec_num,
                        "section_title": block["section_title"],
                        "subsection": subsection,
                        "clause": None,
                        "text": p_text,
                        "has_illustration": "Illustration" in p_text,
                        "has_proviso": any(
                            p in p_text
                            for p in [
                                "Provided that",
                                "Provided further that",
                                "Provided also that",
                            ]
                        ),
                        "has_exception": "Exception" in p_text,
                        "page_start": page_start,
                        "page_end": page_end,
                        "chunk_id": chunk_id,
                        "source_uri": source_uri,
                        "references_json": extract_cross_references(p_text),
                        "needs_review": False,
                    }
                )

    if stats is not None:
        sorted_fallback = sorted(
            list(fallback_sections), key=lambda x: int(x) if x.isdigit() else 9999
        )
        stats["fallback_sections"] = sorted_fallback
        stats["fallback_count"] = len(sorted_fallback)

    return chunks
