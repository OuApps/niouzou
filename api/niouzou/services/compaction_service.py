"""Keyword compaction (E10-S3).

The AI keyword extractor occasionally emits the same entity under near-duplicate
spellings ("FC Barcelone", "Barça", "Barcelona FC"), fragmenting per-user weight
signal across rows that semantically should be one. Compaction asks the LLM to
group those terms and rewrites ``article_keywords`` to use a single canonical
form, then rebuilds ``keyword_weights`` from the now-consistent history.

The flow is two-step on purpose: nothing in the DB changes until the admin
reviews the proposed groups and clicks Apply. The preview is persisted so an
abandoned session can be resumed.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import bindparam, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.models import ArticleKeyword, CompactionRun, KeywordWeight
from niouzou.models.compaction_run import (
    STATUS_APPLIED,
    STATUS_FAILED,
    STATUS_PREVIEW,
    STATUS_REJECTED,
)
from niouzou.services.openrouter_client import OpenRouterClient
from niouzou.services.weights import recompute_all

logger = logging.getLogger("niouzou.compaction")

# Default vocabulary size sent to the LLM. The long tail of rare terms is
# excluded on purpose — that's where the dilution penalty is smallest and the
# token cost grows fastest. 500 covers the heads we care about.
COMPACTION_TOP_N = 500

# E13-S2 — Fallback prompt used when ``llm_prompts.compaction.system`` is
# unavailable (early bootstrap, tests that don't run migrations). The DB
# value loaded by ``CompactionService.preview`` overrides it in normal use.
_COMPACTION_SYSTEM_FALLBACK = (
    "You are a knowledge-base curator. Group keyword terms that refer to the "
    "same concept. Return ONLY "
    '{"groups": [{"canonical": "<preferred>", "aliases": ["<other>"]}]}. '
    "Be conservative. No preamble."
)


@dataclass(slots=True)
class CompactionGroup:
    """One proposed merge: ``aliases`` will be rewritten as ``canonical``."""

    canonical: str
    aliases: list[str]
    skipped_reason: str | None = None


def _parse_groups(data: object) -> list[CompactionGroup]:
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    raw = data.get("groups")
    if not isinstance(raw, list):
        raise ValueError("Missing 'groups' array")
    groups: list[CompactionGroup] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        canonical = item.get("canonical")
        aliases = item.get("aliases")
        if not isinstance(canonical, str) or not isinstance(aliases, list):
            continue
        canonical = canonical.strip().lower()
        cleaned_aliases: list[str] = []
        seen: set[str] = {canonical}
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            normalised = alias.strip().lower()
            if not normalised or normalised in seen:
                continue
            cleaned_aliases.append(normalised)
            seen.add(normalised)
        if not canonical or not cleaned_aliases:
            continue
        groups.append(CompactionGroup(canonical=canonical, aliases=cleaned_aliases))
    return groups


async def _load_top_terms(session: AsyncSession, limit: int) -> list[str]:
    rows = await session.execute(
        select(ArticleKeyword.term)
        .group_by(ArticleKeyword.term)
        .order_by(func.count().desc(), ArticleKeyword.term.asc())
        .limit(limit)
    )
    return list(rows.scalars().all())


class CompactionService:
    """LLM-driven keyword compaction. Owns the preview/apply lifecycle."""

    def __init__(
        self,
        session: AsyncSession,
        client: OpenRouterClient | None = None,
    ) -> None:
        self.session = session
        self._client = client

    @property
    def ai_enabled(self) -> bool:
        return self._client is not None

    async def _load_system_prompt(self) -> str:
        from niouzou.models import LlmPrompt

        row = await self.session.get(LlmPrompt, "compaction.system")
        return row.body if row is not None else _COMPACTION_SYSTEM_FALLBACK

    async def preview(
        self, *, top_n: int = COMPACTION_TOP_N
    ) -> CompactionRun:
        """Ask the LLM to group the top-N terms; persist as a preview row.

        Raises ``RuntimeError`` when AI is disabled (compaction has no
        non-LLM fallback — TF-IDF can't recognise synonyms).
        """
        if self._client is None:
            raise RuntimeError("Compaction requires an OpenRouter API key")

        terms = await _load_top_terms(self.session, top_n)
        if not terms:
            run = CompactionRun(status=STATUS_PREVIEW, groups_json=[])
            self.session.add(run)
            await self.session.flush()
            return run

        prompt = "Terms (one per line):\n" + "\n".join(terms)
        system = await self._load_system_prompt()
        groups = await _call_llm(self._client, system, prompt)
        # Drop groups whose canonical / aliases reference terms outside the
        # vocab we sent — those would be model hallucinations and a silent
        # UPDATE on them could rename rows we never intended to touch.
        known = set(terms)
        filtered = [
            g
            for g in groups
            if g.canonical in known and all(a in known for a in g.aliases)
        ]
        logger.info(
            "compaction.preview: LLM returned %d groups, %d match vocab",
            len(groups),
            len(filtered),
        )

        run = CompactionRun(
            status=STATUS_PREVIEW,
            groups_json=[
                {"canonical": g.canonical, "aliases": list(g.aliases)}
                for g in filtered
            ],
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def reject(self, run_id: uuid.UUID) -> CompactionRun:
        """Mark a preview as rejected so it stops appearing as pending."""
        run = await self.session.get(CompactionRun, run_id)
        if run is None:
            raise ValueError("Compaction run not found")
        if run.status != STATUS_PREVIEW:
            raise ValueError(f"Run is not a preview (status={run.status!r})")
        run.status = STATUS_REJECTED
        await self.session.flush()
        return run

    async def apply(self, run_id: uuid.UUID) -> CompactionRun:
        """Execute the previewed merges + rebuild affected user weights.

        Order matters here:
            1. Annotate ``skipped_reason='pinned'`` on groups that touch a
               ``manually_overridden=true`` term and exclude them.
            2. For each remaining group: pre-resolve PK collisions, then
               ``UPDATE article_keywords SET term=canonical WHERE term IN aliases``.
            3. ``recompute_all`` (same recipe as ``cron_refresh_weights``).
            4. Purge alias rows from ``keyword_weights`` that no longer have a
               matching keyword.

        Everything runs inside the caller's transaction and commits atomically.
        Concurrent ``/feedback`` writes can't resurrect orphans against our
        pre-commit state — they see the old terms until our commit lands, at
        which point the aliases are gone. (A previous version of this code
        called the purge twice "after ~100ms" expecting to catch a race; both
        calls were actually in the same TX so the second pass was inert.
        Removed rather than left as cargo.)

        On any exception, the run row is flipped to ``failed`` and re-raised
        for the caller to log.
        """
        run = await self.session.get(CompactionRun, run_id)
        if run is None:
            raise ValueError("Compaction run not found")
        if run.status != STATUS_PREVIEW:
            raise ValueError(f"Run is not a preview (status={run.status!r})")

        try:
            await _annotate_pinned(self.session, run)
            merged = await _apply_groups(self.session, run)
            await recompute_all(self.session)
            await _purge_orphan_weights(self.session)
            run.status = STATUS_APPLIED
            run.applied_at = datetime.now(timezone.utc)
            run.keywords_merged = merged
            await self.session.flush()
            return run
        except Exception as exc:
            logger.exception("compaction.apply: failed for run %s", run_id)
            run.status = STATUS_FAILED
            run.error = f"{type(exc).__name__}: {exc}"
            await self.session.flush()
            raise


async def _call_llm(
    client: OpenRouterClient, system: str, prompt: str
) -> list[CompactionGroup]:
    """Run the grouping prompt off the event loop (the SDK is blocking)."""
    import asyncio

    def _go() -> list[CompactionGroup]:
        return client.complete_json(
            system=system,
            user=prompt,
            parse=_parse_groups,
            retries=1,
        )

    return await asyncio.to_thread(_go)


async def _annotate_pinned(
    session: AsyncSession, run: CompactionRun
) -> None:
    """Mark groups touching a pinned (manually_overridden) term as skipped.

    Skipping is at the group level: if any user has pinned an alias or the
    canonical, we leave the whole group alone rather than partially merge.
    Partial merges would silently change a user's pinned weight by altering
    which feedbacks contribute to it.
    """
    candidate_terms: set[str] = set()
    for g in run.groups_json:
        candidate_terms.add(g["canonical"])
        candidate_terms.update(g["aliases"])
    if not candidate_terms:
        return

    pinned_rows = (
        await session.execute(
            select(KeywordWeight.term)
            .where(KeywordWeight.manually_overridden.is_(True))
            .where(KeywordWeight.term.in_(candidate_terms))
            .distinct()
        )
    ).scalars().all()
    pinned = set(pinned_rows)
    if not pinned:
        return

    annotated: list[dict] = []
    for g in run.groups_json:
        touched = pinned & ({g["canonical"], *g["aliases"]})
        if touched:
            annotated.append({**g, "skipped_reason": "pinned"})
        else:
            annotated.append(g)
    # JSONB column needs a fresh dict/list assignment to be flagged dirty.
    run.groups_json = annotated


async def _apply_groups(
    session: AsyncSession, run: CompactionRun
) -> int:
    """Rewrite ``article_keywords`` for every non-skipped group.

    Returns the total alias count actually merged (used for telemetry).
    Collisions where the same article carries both canonical and an alias
    are resolved by keeping the row with the higher salience and deleting
    the duplicate before the UPDATE.
    """
    merged = 0
    for g in run.groups_json:
        if g.get("skipped_reason"):
            continue
        canonical: str = g["canonical"]
        aliases: list[str] = list(g["aliases"])
        if not aliases:
            continue

        # 1. Resolve collisions: any article that already has both canonical
        #    AND one of the aliases. Keep the MAX(salience) row, delete the
        #    rest. We do this before UPDATE so the unique PK (article_id, term)
        #    isn't violated when the UPDATE renames an alias to canonical.
        await session.execute(
            text(
                """
                WITH collisions AS (
                    SELECT article_id, MAX(salience) AS max_salience
                    FROM article_keywords
                    WHERE term = :canonical
                       OR term = ANY(CAST(:aliases AS text[]))
                    GROUP BY article_id
                    HAVING COUNT(DISTINCT term) > 1
                ),
                doomed AS (
                    SELECT ak.article_id, ak.term, ak.salience
                    FROM article_keywords ak
                    JOIN collisions c ON c.article_id = ak.article_id
                    WHERE (ak.term = :canonical
                           OR ak.term = ANY(CAST(:aliases AS text[])))
                      AND ak.salience < c.max_salience
                )
                DELETE FROM article_keywords ak
                USING doomed d
                WHERE ak.article_id = d.article_id AND ak.term = d.term
                """
            ),
            {"canonical": canonical, "aliases": aliases},
        )
        # In the (rare) case where canonical and an alias have the same
        # salience, the above leaves both — strip the alias afterwards so the
        # UPDATE below still has nothing to collide with.
        await session.execute(
            text(
                """
                DELETE FROM article_keywords
                WHERE term = ANY(CAST(:aliases AS text[]))
                  AND article_id IN (
                    SELECT article_id FROM article_keywords WHERE term = :canonical
                  )
                """
            ),
            {"canonical": canonical, "aliases": aliases},
        )

        # 2. Rename remaining alias rows to canonical.
        rename_stmt = (
            update(ArticleKeyword)
            .where(ArticleKeyword.term.in_(bindparam("aliases", expanding=True)))
            .values(term=canonical)
        )
        await session.execute(
            rename_stmt,
            {"aliases": aliases},
        )

        merged += len(aliases)
    return merged


async def _purge_orphan_weights(session: AsyncSession) -> None:
    """Delete ``keyword_weights`` rows whose term no longer exists.

    Only touches rows that are NOT pinned — a user's explicit choice survives
    even if the underlying keyword has been compacted away.
    """
    await session.execute(
        text(
            """
            DELETE FROM keyword_weights
            WHERE manually_overridden = false
              AND term NOT IN (SELECT DISTINCT term FROM article_keywords)
            """
        )
    )
