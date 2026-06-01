"""Article detail endpoint: GET /articles/{id}."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from niouzou.deps import CurrentUser
from niouzou.schemas.articles import ArticleDetail, ScoreDebug
from niouzou.services.articles_service import ArticlesService

router = APIRouter(prefix="/articles", tags=["articles"])

ArticlesServiceDep = Annotated[ArticlesService, Depends()]


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: uuid.UUID, user: CurrentUser, service: ArticlesServiceDep
) -> ArticleDetail:
    return await service.get(user.id, article_id)


@router.get("/{article_id}/score-debug", response_model=ScoreDebug)
async def get_score_debug(
    article_id: uuid.UUID, user: CurrentUser, service: ArticlesServiceDep
) -> ScoreDebug:
    """Per-article relevance-score breakdown (E10-S2).

    Returns the scorer name, enrichment model, and the user's weight on each
    of the article's keywords (``null`` when the user has no row for that
    term yet). 403 on cross-user access — never leaks another user's
    ``keyword_weights``.
    """
    return await service.score_debug(user.id, article_id)
