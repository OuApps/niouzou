"""Article endpoints: detail, score debug, and the article chat (E21-S2)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from niouzou.deps import CurrentUser
from niouzou.schemas.articles import ArticleDetail, ScoreDebug
from niouzou.schemas.chat import ChatRequest
from niouzou.services.articles_service import ArticlesService
from niouzou.services.chat_service import ChatService

router = APIRouter(prefix="/articles", tags=["articles"])

ArticlesServiceDep = Annotated[ArticlesService, Depends()]
ChatServiceDep = Annotated[ChatService, Depends()]


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: uuid.UUID, user: CurrentUser, service: ArticlesServiceDep
) -> ArticleDetail:
    return await service.get(user.id, article_id)


@router.get("/{article_id}/score-debug", response_model=ScoreDebug)
async def get_score_debug(
    article_id: uuid.UUID, user: CurrentUser, service: ArticlesServiceDep
) -> ScoreDebug:
    """Per-article relevance-score breakdown (E10-S2, dual since E16-S10).

    Returns both persisted scores with their inputs: the user's weight on
    each of the article's keywords (``null`` when the user has no row for
    that term yet) for the keyword method, and the k-NN neighbours + pinned
    boost for the smart method. 403 on cross-user access — never leaks
    another user's ``keyword_weights``.
    """
    return await service.score_debug(user.id, article_id)


@router.post("/{article_id}/chat")
async def chat(
    article_id: uuid.UUID,
    body: ChatRequest,
    user: CurrentUser,
    service: ChatServiceDep,
) -> StreamingResponse:
    """Discuss the article with the LLM (E21-S2), streamed as SSE.

    ``prepare`` runs every guard up-front (403/404/409 come back as regular
    JSON errors); only then does the token stream start. v1 is stateless —
    the client sends the whole thread on each turn.
    """
    ctx = await service.prepare(user.id, article_id, body.messages)
    return StreamingResponse(
        service.stream(ctx),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tell nginx-style proxies not to buffer the stream.
            "X-Accel-Buffering": "no",
        },
    )
