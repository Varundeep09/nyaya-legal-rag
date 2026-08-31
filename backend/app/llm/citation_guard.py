"""
Post-generation citation validation guard for Nyaya Legal Assistant.
Verifies that all inline citations in LLM responses map directly to
statute sections or user document chunks present in the retrieved context.
Strips hallucinated citations to prevent fabricating authorities.
"""

import re
from typing import List, Dict, Any, Tuple
from app.core.logging import logger

STATUTE_CITATION_PATTERN = re.compile(
    r"\[(BNSS|BNS)\s+s\.([0-9a-zA-Z\(\)]+)\]",
    re.IGNORECASE
)

USER_DOC_CITATION_PATTERN = re.compile(
    r"\[Doc:\s*([^,\]]+?)(?:,\s*p\.(\d+))?\]",
    re.IGNORECASE
)


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
    e.g. ('[BNSS s.35(1)]', 'STATUTE', '35(1)') or ('[Doc: notice.pdf, p.1]', 'USER_DOC', 'notice.pdf')
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

    # Collect valid statute sections and valid user document filenames
    valid_statute_sections = set()
    valid_doc_filenames = set()

    for chunk in retrieved_chunks:
        retrieval_method = chunk.get("retrieval_method", "")
        if retrieval_method == "user_document" or chunk.get("act_short") == "UserDoc":
            fn = str(chunk.get("filename", "")).strip().lower()
            if fn:
                valid_doc_filenames.add(fn)
        else:
            sec = str(chunk.get("section_number", "")).strip()
            if sec:
                valid_statute_sections.add(sec)
                base_match = re.match(r"^(\d+)", sec)
                if base_match:
                    valid_statute_sections.add(base_match.group(1))

    valid = []
    hallucinated = []

    for cit in citations:
        # Check if it's a user document citation
        if cit.startswith("Doc:"):
            # Extract filename from 'Doc: filename.pdf, p.1'
            doc_match = re.match(r"^Doc:\s*([^,]+)", cit)
            doc_name = doc_match.group(1).strip().lower() if doc_match else ""
            if doc_name in valid_doc_filenames:
                valid.append(cit)
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
                "CITATION GUARD TRIGGERED: Stripping hallucinated %s citation '%s' for query '%s'.",
                cit_type, full_token, query
            )
            sanitized_text = sanitized_text.replace(full_token, "")

    # Clean up double whitespace left by stripped tokens
    sanitized_text = re.sub(r"[ \t]+", " ", sanitized_text).strip()

    return sanitized_text, valid_ids, hallucinated_ids
