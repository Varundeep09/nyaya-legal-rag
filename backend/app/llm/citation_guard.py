"""
Post-generation citation validation guard for Nyaya Legal Assistant.
Verifies that all inline citations in LLM responses map directly to
statute sections or user document chunks present in the retrieved context.
Strips hallucinated citations to prevent fabricating authorities.
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from app.core.logging import logger

STATUTE_CITATION_PATTERN = re.compile(
    r"\[(BNSS|BNS)\s+s\.([0-9a-zA-Z\(\)]+)\]",
    re.IGNORECASE
)

USER_DOC_CITATION_PATTERN = re.compile(
    r"\[Doc:\s*([^,\]]+?)(?:,\s*p\.(\d+))?\]",
    re.IGNORECASE
)


def extract_doc_citations(generated_text: str) -> List[Tuple[str, Optional[int]]]:
    """
    Regex extracts every '[Doc: <filename>, p.<page>]' or '[Doc: <filename>]' citation.
    Returns a list of (filename, page_number) tuples.
    """
    if not generated_text:
        return []
    doc_citations = []
    for m in USER_DOC_CITATION_PATTERN.finditer(generated_text):
        filename = m.group(1).strip()
        page_str = m.group(2)
        page_num = int(page_str) if page_str else None
        doc_citations.append((filename, page_num))
    return doc_citations


def validate_doc_citations(
    doc_citations: List[Tuple[str, Optional[int]]],
    retrieved_user_chunks: List[Dict[str, Any]]
) -> Tuple[List[Tuple[str, Optional[int]]], List[Tuple[str, Optional[int]]]]:
    """
    Validates that each cited (filename, page_number) pair actually matches a
    filename and page_number that was present in the retrieved user document chunks
    sent to the LLM for this request.
    
    A citation referencing a filename never uploaded/retrieved, or a page number
    that the retrieved chunks never came from, is marked invalid.
    
    Returns:
        Tuple of (valid_doc_citations, invalid_doc_citations)
    """
    if not doc_citations:
        return [], []

    # Map filename_lower -> set of valid page numbers retrieved
    valid_retrieved_map: Dict[str, set] = {}
    for chunk in retrieved_user_chunks:
        retrieval_method = chunk.get("retrieval_method", "")
        act_short = chunk.get("act_short", "")
        if retrieval_method == "user_document" or act_short == "UserDoc":
            fn = str(chunk.get("filename", "")).strip().lower()
            page = chunk.get("page_number") or chunk.get("page_start")
            if fn:
                if fn not in valid_retrieved_map:
                    valid_retrieved_map[fn] = set()
                if page is not None:
                    valid_retrieved_map[fn].add(int(page))

    valid: List[Tuple[str, Optional[int]]] = []
    invalid: List[Tuple[str, Optional[int]]] = []

    for fn, page in doc_citations:
        fn_clean = fn.strip().lower()
        if fn_clean not in valid_retrieved_map:
            invalid.append((fn, page))
        elif page is not None and valid_retrieved_map[fn_clean] and page not in valid_retrieved_map[fn_clean]:
            # Cited a page number not in retrieved chunks for this file
            invalid.append((fn, page))
        else:
            valid.append((fn, page))

    return valid, invalid


def extract_citations(generated_text: str) -> List[str]:
    """
    Extracts all citation strings from generated response text.
    Returns list of section/document identifiers, e.g. ['35(1)', '65(1)', 'Doc: notice.pdf, p.1'].
    """
    if not generated_text:
        return []
    citations = []

    # 1. Statute citations
    for m in STATUTE_CITATION_PATTERN.finditer(generated_text):
        citations.append(m.group(2))

    # 2. User document citations
    for m in USER_DOC_CITATION_PATTERN.finditer(generated_text):
        filename = m.group(1).strip()
        page = m.group(2)
        if page:
            citations.append(f"Doc: {filename}, p.{page}")
        else:
            citations.append(f"Doc: {filename}")

    return citations


def extract_full_citation_matches(generated_text: str) -> List[Tuple[str, str, str]]:
    """
    Extracts (full_token, citation_type, identifier) tuples.
    e.g. ('[BNSS s.35(1)]', 'STATUTE', '35(1)') or ('[Doc: notice.pdf, p.1]', 'USER_DOC', 'Doc: notice.pdf, p.1')
    """
    if not generated_text:
        return []
    results = []

    for m in STATUTE_CITATION_PATTERN.finditer(generated_text):
        results.append((m.group(0), "STATUTE", m.group(2)))

    for m in USER_DOC_CITATION_PATTERN.finditer(generated_text):
        filename = m.group(1).strip()
        page = m.group(2)
        ident = f"Doc: {filename}, p.{page}" if page else f"Doc: {filename}"
        results.append((m.group(0), "USER_DOC", ident))

    return results


def validate_citations(
    citations: List[str],
    retrieved_chunks: List[Dict[str, Any]]
) -> Tuple[List[str], List[str]]:
    """
    Checks each extracted citation identifier against sections and documents
    present in the specific retrieved context chunks sent to the LLM.
    
    Returns:
        Tuple of (valid_citations, hallucinated_citations)
    """
    if not citations:
        return [], []

    # Collect valid statute sections and valid user document filename+page pairs
    valid_statute_sections = set()
    user_doc_chunks = []

    for chunk in retrieved_chunks:
        retrieval_method = chunk.get("retrieval_method", "")
        if retrieval_method == "user_document" or chunk.get("act_short") == "UserDoc":
            user_doc_chunks.append(chunk)
        else:
            sec = str(chunk.get("section_number", "")).strip()
            if sec:
                valid_statute_sections.add(sec)
                base_match = re.match(r"^(\d+)", sec)
                if base_match:
                    valid_statute_sections.add(base_match.group(1))

    valid = []
    hallucinated = []

    # Validate doc citations using validate_doc_citations
    doc_cits_raw = [c for c in citations if c.startswith("Doc:")]
    parsed_doc_tuples = []
    for d in doc_cits_raw:
        m = re.match(r"^Doc:\s*([^,]+)(?:,\s*p\.(\d+))?", d)
        if m:
            fn = m.group(1).strip()
            page = int(m.group(2)) if m.group(2) else None
            parsed_doc_tuples.append((d, (fn, page)))

    valid_doc_tuples, invalid_doc_tuples = validate_doc_citations(
        [t[1] for t in parsed_doc_tuples],
        user_doc_chunks
    )
    valid_doc_set = set(valid_doc_tuples)

    for cit in citations:
        if cit.startswith("Doc:"):
            # Check if this doc citation tuple was valid
            m = re.match(r"^Doc:\s*([^,]+)(?:,\s*p\.(\d+))?", cit)
            if m:
                fn = m.group(1).strip()
                page = int(m.group(2)) if m.group(2) else None
                if (fn, page) in valid_doc_set:
                    valid.append(cit)
                else:
                    hallucinated.append(cit)
            else:
                hallucinated.append(cit)
        else:
            # Statute section check
            base_cit_match = re.match(r"^(\d+)", cit)
            base_cit = base_cit_match.group(1) if base_cit_match else cit
            if cit in valid_statute_sections or base_cit in valid_statute_sections:
                valid.append(cit)
            else:
                hallucinated.append(cit)

    return valid, hallucinated


def sanitize_response(
    generated_text: str,
    retrieved_chunks: List[Dict[str, Any]],
    query: str = ""
) -> Tuple[str, List[str], List[str]]:
    """
    Validates all citations in generated text against retrieved chunks.
    Strips hallucinated citations from the output text and logs warnings.
    
    Returns:
        Tuple of (sanitized_text, valid_citations, hallucinated_citations)
    """
    if not generated_text:
        return "", [], []

    citation_matches = extract_full_citation_matches(generated_text)
    citation_ids = [m[2] for m in citation_matches]
    valid_ids, hallucinated_ids = validate_citations(citation_ids, retrieved_chunks)

    sanitized_text = generated_text

    # Strip any hallucinated citation tokens
    for full_token, cit_type, ident in citation_matches:
        if ident in hallucinated_ids:
            logger.warning(
                "CITATION GUARD TRIGGERED: Stripping hallucinated %s citation '%s' (ident '%s') for query '%s'.",
                cit_type, full_token, ident, query
            )
            sanitized_text = sanitized_text.replace(full_token, "")

    # Clean up double whitespace left by stripped tokens
    sanitized_text = re.sub(r"[ \t]+", " ", sanitized_text).strip()

    return sanitized_text, valid_ids, hallucinated_ids
