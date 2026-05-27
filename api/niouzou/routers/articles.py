"""Article detail endpoint: GET /articles/{id}."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from niouzou.deps import CurrentUser
from niouzou.schemas.articles import ArticleDetail
from niouzou.services.articles_service import ArticlesService

router = APIRouter(prefix="/articles", tags=["articles"])

ArticlesServiceDep = Annotated[ArticlesService, Depends()]


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: uuid.UUID, user: CurrentUser, service: ArticlesServiceDep
) -> ArticleDetail:
    return await service.get(user.id, article_id)
