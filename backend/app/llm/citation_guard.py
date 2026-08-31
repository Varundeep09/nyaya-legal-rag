"""
Post-generation citation validation guard for Nyaya Legal Assistant.
Verifies that all inline citations in LLM responses map directly to
sections present in the retrieved context chunks for that specific turn.
Strips hallucinated citations to prevent fabricating statutory authorities.
"""

import re
from typing import List, Dict, Any, Tuple
from app.core.logging import logger

# Regex matching [BNSS s.35], [BNSS s.35(1)], [BNS s.64(2)], [BNS s.65(1)]
CITATION_PATTERN = re.compile(
    r"\[(BNSS|BNS)\s+s\.([0-9a-zA-Z\(\)]+)\]",
    re.IGNORECASE
)


def extract_citations(generated_text: str) -> List[str]:
    """
    Extracts all citation strings from generated response text.
    Returns list of section identifiers, e.g. ['35(1)', '65(1)'].
    """
    if not generated_text:
        return []
    matches = CITATION_PATTERN.findall(generated_text)
    return [m[1] for m in matches]


def extract_full_citation_matches(generated_text: str) -> List[Tuple[str, str, str]]:
    """
    Extracts (full_citation_string, act_short, section_identifier) tuples.
    e.g. [('[BNSS s.35(1)]', 'BNSS', '35(1)'), ('[BNSS s.999]', 'BNSS', '999')]
    """
    if not generated_text:
        return []
    results = []
    for match in CITATION_PATTERN.finditer(generated_text):
        full_token = match.group(0)
        act = match.group(1).upper()
        sec = match.group(2)
        results.append((full_token, act, sec))
    return results


def validate_citations(
    citations: List[str],
    retrieved_chunks: List[Dict[str, Any]]
) -> Tuple[List[str], List[str]]:
    """
    Checks each extracted section identifier against section numbers present
    in the specific retrieved context chunks sent to the LLM.
    
    Returns:
        Tuple of (valid_citations, hallucinated_citations)
    """
    if not citations:
        return [], []

    # Collect all valid section identifiers from retrieved chunks
    valid_sections = set()
    for chunk in retrieved_chunks:
        sec = str(chunk.get("section_number", "")).strip()
        if sec:
            valid_sections.add(sec)
            # Also register base number (e.g. '35' for '35(1)')
            base_match = re.match(r"^(\d+)", sec)
            if base_match:
                valid_sections.add(base_match.group(1))

    valid = []
    hallucinated = []

    for cit in citations:
        base_cit_match = re.match(r"^(\d+)", cit)
        base_cit = base_cit_match.group(1) if base_cit_match else cit

        if cit in valid_sections or base_cit in valid_sections:
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
    for full_token, act, sec in citation_matches:
        if sec in hallucinated_ids:
            logger.warning(
                "CITATION GUARD TRIGGERED: Stripping hallucinated citation '%s' for query '%s'. "
                "Retrieved valid sections: %s",
                full_token,
                query,
                [c.get("section_number") for c in retrieved_chunks]
            )
            # Remove the hallucinated citation token
            sanitized_text = sanitized_text.replace(full_token, "")

    # Clean up double whitespace left by stripped tokens
    sanitized_text = re.sub(r"[ \t]+", " ", sanitized_text).strip()

    return sanitized_text, valid_ids, hallucinated_ids
