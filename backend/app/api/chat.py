"""
Chat endpoint for Nyaya Legal Assistant.
Provides SSE token streaming, RAG context injection, refusal gating,
citation verification guarding, and chat history persistence.
"""

import json
from typing import AsyncGenerator, List, Dict, Any
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db, AsyncSessionLocal
from app.core.logging import logger
from app.core.models import ChatSession, ChatMessage
from app.retrieval.hybrid_retriever import hybrid_search
from app.retrieval.refusal import should_refuse, REFUSAL_MESSAGE
from app.llm.prompts import NYAYA_SYSTEM_PROMPT, build_rag_prompt
from app.llm.provider import get_llm_provider
from app.llm.citation_guard import sanitize_response

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User legal query or message")
    session_id: str = Field(default="default-session", description="Unique session identifier")


async def persist_chat_turn(
    session_id: str,
    user_message: str,
    assistant_response: str,
    citations: List[str]
) -> None:
    """
    Persists user message and assistant turn with verified citations into PostgreSQL.
    """
    try:
        async with AsyncSessionLocal() as db:
            # Ensure chat session exists
            stmt = select(ChatSession).where(ChatSession.id == session_id)
            res = await db.execute(stmt)
            session_obj = res.scalar_one_or_none()

            if not session_obj:
                session_obj = ChatSession(id=session_id)
                db.add(session_obj)
                await db.flush()

            # Insert user turn
            user_msg = ChatMessage(
                session_id=session_id,
                role="user",
                content=user_message,
                citations_json=[]
            )
            db.add(user_msg)

            # Insert assistant turn
            assistant_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=assistant_response,
                citations_json=citations
            )
            db.add(assistant_msg)

            await db.commit()
            logger.info("Persisted chat turn for session_id '%s' (%d citations).", session_id, len(citations))
    except Exception as e:
        logger.error("Failed to persist chat turn to database: %s", e)


async def chat_event_stream(
    message: str,
    session_id: str
) -> AsyncGenerator[str, None]:
    """
    Asynchronously streams SSE events for a single chat turn.
    """
    # 1. Retrieve statutory & classification context
    async with AsyncSessionLocal() as session:
        retrieved_chunks = await hybrid_search(session, message, top_k=5)

    # 2. Evaluate refusal threshold
    if should_refuse(retrieved_chunks):
        logger.info("Chat query refused: '%s'", message)
        
        # Stream refusal message tokens
        words = REFUSAL_MESSAGE.split(" ")
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            payload = json.dumps({"event": "token", "data": token})
            yield f"data: {payload}\n\n"

        # Emit refusal event
        yield f"data: {json.dumps({'event': 'refusal', 'data': True})}\n\n"
        yield f"data: {json.dumps({'event': 'sources', 'data': []})}\n\n"
        yield f"data: {json.dumps({'event': 'done', 'data': {'session_id': session_id, 'refused': True, 'citations': []}})}\n\n"

        # Persist refusal turn
        await persist_chat_turn(session_id, message, REFUSAL_MESSAGE, [])
        return

    # 3. Build RAG prompt with retrieved context
    prompt = build_rag_prompt(message, retrieved_chunks)
    provider = get_llm_provider()

    accumulated_tokens: List[str] = []

    # 4. Stream LLM tokens
    try:
        async for token in provider.generate_stream(
            prompt=prompt,
            system_prompt=NYAYA_SYSTEM_PROMPT,
            context_chunks=retrieved_chunks
        ):
            if token:
                accumulated_tokens.append(token)
                payload = json.dumps({"event": "token", "data": token})
                yield f"data: {payload}\n\n"
    except Exception as e:
        logger.error("Generation stream exception: %s", e)
        err_msg = "\n[Generation error encountered; streaming stopped.]"
        accumulated_tokens.append(err_msg)
        yield f"data: {json.dumps({'event': 'token', 'data': err_msg})}\n\n"

    full_generated_text = "".join(accumulated_tokens)

    # 5. Post-generation citation validation guard
    sanitized_text, valid_citations, hallucinated_citations = sanitize_response(
        full_generated_text,
        retrieved_chunks,
        query=message
    )

    if hallucinated_citations:
        guard_event = {
            "event": "guard_warning",
            "data": {
                "message": "Hallucinated citations detected and stripped.",
                "hallucinated_citations": hallucinated_citations
            }
        }
        yield f"data: {json.dumps(guard_event)}\n\n"

    # 6. Emit source drawer metadata
    sources_metadata = []
    for chunk in retrieved_chunks:
        sources_metadata.append({
            "chunk_id": chunk.get("chunk_id"),
            "act": chunk.get("act"),
            "act_short": chunk.get("act_short"),
            "section_number": chunk.get("section_number"),
            "section_title": chunk.get("section_title"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "score": chunk.get("score"),
            "retrieval_method": chunk.get("retrieval_method")
        })

    yield f"data: {json.dumps({'event': 'sources', 'data': sources_metadata})}\n\n"

    # 7. Emit model call proof metadata
    yield f"data: {json.dumps({'event': 'model_proof', 'data': provider.last_call_metadata})}\n\n"

    # 8. Emit final done event
    done_payload = {
        "event": "done",
        "data": {
            "session_id": session_id,
            "refused": False,
            "citations": valid_citations,
            "stripped_hallucinations": hallucinated_citations,
            "model_proof": provider.last_call_metadata
        }
    }
    yield f"data: {json.dumps(done_payload)}\n\n"

    # 9. Persist chat turn to DB
    await persist_chat_turn(session_id, message, sanitized_text, valid_citations)



@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    SSE streaming chat endpoint.
    Retrieves legal statute context, gates against off-topic queries,
    streams LLM tokens, validates citations, and persists turn history.
    """
    logger.info("Incoming chat request for session '%s': '%s'", request.session_id, request.message)
    return StreamingResponse(
        chat_event_stream(request.message, request.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
