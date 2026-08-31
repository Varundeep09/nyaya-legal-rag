"""
Prompt engineering templates and citation contract system prompts for Nyaya Legal Assistant.
"""

from typing import List, Dict, Any

NYAYA_SYSTEM_PROMPT = """You are Nyaya, an expert AI Legal Assistant specializing strictly in the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) and the Bharatiya Nyaya Sanhita, 2023 (BNS) First Schedule offence classifications.

CRITICAL CITATION AND GROUNDING RULES:
1. Answer ONLY from the provided retrieved statutory context chunks below. NEVER use ungrounded parametric knowledge or external legal assumptions.
2. Every legal assertion, procedure, right, power, or punishment MUST carry an immediate inline citation in one of these exact formats:
   - For BNSS criminal procedure sections: [BNSS s.<section_number>] or [BNSS s.<section_number>(<subsection>)] (e.g., [BNSS s.35(1)], [BNSS s.103(3)], [BNSS s.480]).
   - For BNS substantive offence classifications: [BNS s.<bns_section>] (e.g., [BNS s.64(2)], [BNS s.65(1)]).
3. Copy the exact citation keys provided with each context block. Do NOT invent, extrapolate, or hallucinate section numbers not present in the retrieved chunks.
4. If the provided context does not contain sufficient statutory details to answer the user's question completely, state clearly: "The provided statutory sections do not contain enough verified information to answer this question." Do NOT guess or speculate.
5. Be concise, precise, and objective. State legal provisions directly with their accompanying citations."""


def format_chunk_citation_key(chunk: Dict[str, Any]) -> str:
    """
    Constructs the canonical citation key for a given statute or schedule chunk.
    """
    act_short = chunk.get("act_short", "BNSS")
    sec_num = chunk.get("section_number", "")
    subsec = chunk.get("subsection")

    if act_short == "BNS":
        return f"[BNS s.{sec_num}]"

    # BNSS statute chunk
    if subsec and subsec.startswith("("):
        return f"[BNSS s.{sec_num}{subsec}]"
    return f"[BNSS s.{sec_num}]"


def build_rag_prompt(query: str, context_chunks: List[Dict[str, Any]]) -> str:
    """
    Constructs the complete RAG prompt presenting the retrieved legal context
    labeled clearly with its citation keys followed by the user question.
    """
    context_blocks = []
    for idx, chunk in enumerate(context_chunks, start=1):
        citation_key = format_chunk_citation_key(chunk)
        act_title = chunk.get("act", "Bharatiya Nagarik Suraksha Sanhita, 2023")
        sec_title = chunk.get("section_title") or f"Section {chunk.get('section_number', '')}"
        page = chunk.get("page_start", "")

        header = f"--- SOURCE {idx}: {citation_key} ({act_title}, {sec_title}, Page {page}) ---"
        body = chunk.get("text", "").strip()
        context_blocks.append(f"{header}\n{body}")

    formatted_context = "\n\n".join(context_blocks)

    return f"""RETRIEVED STATUTORY CONTEXT:
{formatted_context}

USER QUESTION:
{query}

ANSWER (ensure every legal claim is grounded with its exact inline citation):"""
