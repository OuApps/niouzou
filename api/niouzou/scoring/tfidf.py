"""TF-IDF keyword extraction — the no-AI default scorer.

Dependency-free on purpose: a self-hosted instance shouldn't need numpy/scipy
just to rank words. Salience is TF (within the article) optionally weighted by
IDF (across a supplied corpus), then min-max normalised so the most salient
term is 1.0.

When no corpus is given, IDF is a constant 1.0 and salience reduces to
normalised term frequency — a sensible single-document fallback.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence

from niouzou.scoring.base import BaseScorer, ScoredKeyword

# Words of length >= 3, starting with a letter; keeps tokens like "c++" out but
# allows "rust", "web3". Lowercased before matching.
_TOKEN_RE = re.compile(r"[a-z][a-z0-9]{2,}")

# Small English stoplist — enough to keep extraction from being dominated by
# function words without shipping a full NLP corpus.
_STOPWORDS = frozenset(
    """
    the a an and or but if then else when while for to of in on at by with from
    into over after before about as is are was were be been being have has had do
    does did will would shall should can could may might must not no nor so than
    too very this that these those it its it's they them their there here what which
    who whom whose how why where you your yours we our ours us i me my mine he she
    his her hers him also more most some such only own same out up down off again
    once just now new get got like one two three first new news said says
    """.split()
)


class TFIDFScorer(BaseScorer):
    def __init__(self, max_keywords: int = 25) -> None:
        self.max_keywords = max_keywords

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [
            tok
            for tok in _TOKEN_RE.findall(text.lower())
            if tok not in _STOPWORDS
        ]

    def _idf(self, corpus: Sequence[str]) -> dict[str, float]:
        n = len(corpus)
        doc_freq: Counter[str] = Counter()
        for doc in corpus:
            for term in set(self._tokenize(doc)):
                doc_freq[term] += 1
        # Smoothed IDF: ln((1 + n) / (1 + df)) + 1 — always positive.
        return {
            term: math.log((1 + n) / (1 + df)) + 1.0 for term, df in doc_freq.items()
        }

    def extract_keywords(
        self, text: str, *, corpus: Sequence[str] | None = None
    ) -> list[ScoredKeyword]:
        tokens = self._tokenize(text)
        if not tokens:
            return []

        tf = Counter(tokens)
        max_tf = max(tf.values())
        idf = self._idf(corpus) if corpus else {}

        raw = {
            term: (count / max_tf) * idf.get(term, 1.0) for term, count in tf.items()
        }
        ranked = sorted(raw.items(), key=lambda kv: (-kv[1], kv[0]))[: self.max_keywords]

        top_score = ranked[0][1] or 1.0
        return [
            ScoredKeyword(term=term, salience=round(score / top_score, 4))
            for term, score in ranked
        ]
