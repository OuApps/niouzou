"""Tags business logic (E24): per-user CRUD + per-tag threshold.

Tags are a per-user resource (like sources), created on the fly from the
Sources screen. The per-tag ``threshold`` is the real payoff of the Loupe: it
overrides the instance-wide SCORE_THRESHOLD on GET /feed?tag= only — everywhere
else the tag is a pure source filter. Assignment (tag <-> source) lives in
SourcesService since it returns a SourceOut.
"""

import uuid

from sqlalchemy import func, select

from niouzou.deps import SessionDep
from niouzou.errors import APIError, conflict, not_found
from niouzou.models import Source, SourceTag, Tag
from niouzou.schemas.tags import TagOut, TagsListResponse, TagUpdate


class TagsService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def require_owned(
        self, user_id: uuid.UUID, tag_id: uuid.UUID
    ) -> Tag:
        """Return the tag or raise 422 — the Loupe's ownership gate.

        Same contract as ``source_ids`` on Explore (E11): an unknown or
        foreign tag id is a validation error, never a silent no-filter. A tag
        deleted while selected client-side lands here too; the PWA falls back
        to "no Loupe" on the 422.
        """
        tag = await self.session.scalar(
            select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        )
        if tag is None:
            raise APIError(422, "validation_error", f"Unknown tag id: {tag_id}")
        return tag

    async def list_tags(self, user_id: uuid.UUID) -> TagsListResponse:
        counts = await self._source_counts(user_id)
        rows = (
            await self.session.scalars(
                select(Tag)
                .where(Tag.user_id == user_id)
                .order_by(func.lower(Tag.name))
            )
        ).all()
        return TagsListResponse(
            tags=[
                TagOut(
                    id=t.id,
                    name=t.name,
                    threshold=t.threshold,
                    source_count=counts.get(t.id, 0),
                )
                for t in rows
            ]
        )

    async def _source_counts(self, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Tag id → number of ACTIVE sources carrying it (paused excluded)."""
        rows = (
            await self.session.execute(
                select(SourceTag.tag_id, func.count().label("n"))
                .join(Source, Source.id == SourceTag.source_id)
                .join(Tag, Tag.id == SourceTag.tag_id)
                .where(Tag.user_id == user_id, Source.deleted_at.is_(None))
                .group_by(SourceTag.tag_id)
            )
        ).all()
        return {r.tag_id: r.n for r in rows}

    async def _name_taken(
        self,
        user_id: uuid.UUID,
        name: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        query = select(Tag.id).where(
            Tag.user_id == user_id,
            func.lower(Tag.name) == name.lower(),
        )
        if exclude_id is not None:
            query = query.where(Tag.id != exclude_id)
        return (await self.session.scalar(query)) is not None

    async def create_tag(
        self,
        user_id: uuid.UUID,
        name: str,
        threshold: float | None = None,
    ) -> TagOut:
        if await self._name_taken(user_id, name):
            raise conflict("A tag with this name already exists")
        tag = Tag(user_id=user_id, name=name, threshold=threshold)
        self.session.add(tag)
        await self.session.flush()
        return TagOut(
            id=tag.id, name=tag.name, threshold=tag.threshold, source_count=0
        )

    async def update_tag(
        self, user_id: uuid.UUID, tag_id: uuid.UUID, body: TagUpdate
    ) -> TagOut:
        tag = await self.session.scalar(
            select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        )
        if tag is None:
            raise not_found("Tag not found")

        if body.name is not None:
            if await self._name_taken(user_id, body.name, exclude_id=tag.id):
                raise conflict("A tag with this name already exists")
            tag.name = body.name
        # An explicit ``threshold: null`` reverts to inheriting the global
        # SCORE_THRESHOLD — model_fields_set tells it apart from an absent key.
        if "threshold" in body.model_fields_set:
            tag.threshold = body.threshold
        await self.session.flush()

        counts = await self._source_counts(user_id)
        return TagOut(
            id=tag.id,
            name=tag.name,
            threshold=tag.threshold,
            source_count=counts.get(tag.id, 0),
        )

    async def delete_tag(self, user_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        """Delete the tag; source_tags rows go with it via FK CASCADE.
        Articles are never touched."""
        tag = await self.session.scalar(
            select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        )
        if tag is None:
            raise not_found("Tag not found")
        await self.session.delete(tag)
