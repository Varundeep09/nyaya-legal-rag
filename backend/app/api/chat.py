"""
Chat streaming endpoint with dual-corpus RAG retrieval (statute law + session-isolated user documents),
refusal gating, SSE token streaming, citation validation guard, and history persistence.
"""

import json
from typing import AsyncGenerator, List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.db import AsyncSessionLocal
from app.core.logging import logger
from app.core.models import ChatSession, ChatMessage, UserDocument
from app.core.session import get_session_id_from_header, ensure_session_exists
from app.core.limiter import limiter
from app.core.metrics import QUERY_REFUSALS
from app.retrieval.hybrid_retriever import hybrid_search, search_user_documents
from app.retrieval.refusal import should_refuse, REFUSAL_MESSAGE
from app.llm.prompts import build_rag_prompt, NYAYA_SYSTEM_PROMPT
from app.llm.provider import get_llm_provider
from app.llm.citation_guard import sanitize_response

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="User legal query")
    session_id: Optional[str] = Field(None, description="Session identifier for multi-turn history & user docs")


async def persist_chat_turn(
    session_id: str,
    user_message: str,
    assistant_response: str,
    citations: List[str]
) -> None:
    """Persists a complete turn (user query + assistant response) to PostgreSQL."""
    try:
        async with AsyncSessionLocal() as db:
            # Ensure chat_session row exists
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
    Asynchronously streams SSE events for a single chat turn with dual-corpus routing.
    """
    # 1. Retrieve statutory & user document context
    statute_chunks: List[Dict[str, Any]] = []
    user_doc_chunks: List[Dict[str, Any]] = []

    async with AsyncSessionLocal() as session:
        # A. Hybrid Statute Search (BNSS + BNS First Schedule)
        statute_chunks = await hybrid_search(session, message, top_k=5)

        # B. Check if current session has any ready uploaded documents
        stmt_docs = select(UserDocument.id).where(
            UserDocument.session_id == session_id,
            UserDocument.status == "ready"
        ).limit(1)
        res_docs = await session.execute(stmt_docs)
        has_ready_docs = res_docs.scalar_one_or_none() is not None

        if has_ready_docs:
            user_doc_chunks = await search_user_documents(session, session_id, message, top_k=3)

    # 2. Evaluate refusal threshold
    # If user has uploaded documents matching the query (score >= 0.45) or statute matches pass threshold, do not refuse.
    user_doc_has_strong_match = any(c.get("score", 0.0) >= 0.45 for c in user_doc_chunks)

    if not user_doc_has_strong_match and should_refuse(statute_chunks):
        logger.info("Chat query refused: '%s' (session '%s')", message, session_id)
        QUERY_REFUSALS.inc()
        
        words = REFUSAL_MESSAGE.split(" ")
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            payload = json.dumps({"event": "token", "data": token})
            yield f"data: {payload}\n\n"

        yield f"data: {json.dumps({'event': 'refusal', 'data': True})}\n\n"
        yield f"data: {json.dumps({'event': 'sources', 'data': []})}\n\n"
        yield f"data: {json.dumps({'event': 'done', 'data': {'session_id': session_id, 'refused': True, 'citations': [], 'estimated_cost_usd': 0.0}})}\n\n"

        await persist_chat_turn(session_id, message, REFUSAL_MESSAGE, [])
        return

    # Combine context chunks: User document chunks first, then statute chunks
    all_context_chunks = user_doc_chunks + statute_chunks

    # 3. Build RAG prompt with retrieved context
    prompt = build_rag_prompt(message, all_context_chunks)
    provider = get_llm_provider()

    accumulated_tokens: List[str] = []

    # 4. Stream LLM tokens
    try:
        async for token in provider.generate_stream(
            prompt=prompt,
            system_prompt=NYAYA_SYSTEM_PROMPT,
            context_chunks=all_context_chunks
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
        all_context_chunks,
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
    for chunk in all_context_chunks:
        sources_metadata.append({
            "chunk_id": chunk.get("chunk_id"),
            "act": chunk.get("act"),
            "act_short": chunk.get("act_short"),
            "section_number": chunk.get("section_number"),
            "section_title": chunk.get("section_title"),
            "filename": chunk.get("filename"),
            "page_number": chunk.get("page_number"),
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
            "model_proof": provider.last_call_metadata,
            "estimated_cost_usd": provider.last_call_metadata.get("estimated_cost_usd", 0.0)
        }
    }
    yield f"data: {json.dumps(done_payload)}\n\n"

    # 9. Persist chat turn to DB
    await persist_chat_turn(session_id, message, sanitized_text, valid_citations)


@router.post("/chat")
@limiter.limit("20/minute")
async def chat_endpoint(
    request: Request,
    body: ChatRequest,
    header_session_id: str = Depends(get_session_id_from_header)
):
    """
    SSE streaming chat endpoint supporting dual-corpus RAG.
    Retrieves legal statute and user document context, streams LLM tokens,
    validates citations, and persists turn history.
    """
    effective_session_id = body.session_id if body.session_id else header_session_id
    logger.info("Incoming chat request for session '%s': '%s'", effective_session_id, body.message)

    return StreamingResponse(
        chat_event_stream(body.message, effective_session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-ID": effective_session_id
        }
    )


@router.get("/conversations")
async def list_conversations():
    """Returns all chat sessions ordered by creation date."""
    async with AsyncSessionLocal() as session:
        stmt = select(ChatSession).order_by(ChatSession.created_at.desc())
        res = await session.execute(stmt)
        sessions = res.scalars().all()
        
        convos = []
        for s in sessions:
            msg_stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == s.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
            )
            msg_res = await session.execute(msg_stmt)
            last_msg = msg_res.scalar_one_or_none()
            convos.append({
                "session_id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_message": last_msg.content[:60] if last_msg else "New Chat"
            })
        return convos


@router.get("/conversations/{session_id}/messages")
async def get_conversation_messages(session_id: str):
    """Returns message history for a specific conversation session."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        res = await session.execute(stmt)
        msgs = res.scalars().all()
        return [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "citations": m.citations_json,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in msgs
        ]


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str):
    """Deletes a chat conversation and all its messages."""
    async with AsyncSessionLocal() as session:
        # Delete associated messages
        msg_stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
        msg_res = await session.execute(msg_stmt)
        for m in msg_res.scalars().all():
            await session.delete(m)

        stmt = select(ChatSession).where(ChatSession.id == session_id)
        res = await session.execute(stmt)
        s = res.scalar_one_or_none()
        if s:
            await session.delete(s)
        await session.commit()
        return {"status": "deleted", "session_id": session_id}

