#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BM25 Runbook 检索器 — 纯标准库，无第三方依赖。

设计目标：precision 优先。下游有 LLM 做 runbook selection，检索层宁可弃权
（返回空，走正常流程），也不返回低质量候选。

流水线：
  分词 → 截断 IDF 加权 → 排名分取 max → 覆盖率门禁 → 自适应返回
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import List

# ── 参数 ──────────────────────────────────────────────

COVERAGE_STRONG = 0.40
COVERAGE_WEAK = 0.15
UNSEEN_WEIGHT_RATIO = 0.2

BM25_K1 = 1.2
BM25_B = 0.4
STRONG_SCORE_MARGIN = 0.5
GENERIC_DF_RATIO = 0.6
NEAR_FULL_COVERAGE = 0.8
MAX_STRONG_RESULTS = 5
MAX_WEAK_RESULTS = 10

STOPCHARS = "的了和吗呢吧啊"

_ASCII_TOKEN = re.compile(r"[a-z0-9][a-z0-9._\-]*")
_ASCII_SEP = re.compile(r"[._\-]")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_STOPCHAR_SPLIT = re.compile("[%s]" % STOPCHARS)


@dataclass
class Candidate:
    """一条 BM25 检索结果。"""
    id: str
    tier: str  # "strong" / "weak"
    score: float
    coverage: float


# ── 分词 ──────────────────────────────────────────────

def tokenize(text: str) -> list:
    """ASCII 串整体保留并切子 token；中文按虚字切段后 bigram。"""
    text = text.lower()
    tokens = []
    for match in _ASCII_TOKEN.findall(text):
        tokens.append(match)
        tokens.extend(p for p in _ASCII_SEP.split(match) if p and p != match)
    for run in _CJK_RUN.findall(text):
        for segment in _STOPCHAR_SPLIT.split(run):
            if len(segment) == 1:
                tokens.append(segment)
            elif segment:
                tokens.extend(segment[i:i + 2] for i in range(len(segment) - 1))
    return tokens


def _same_word(a: str, b: str) -> bool:
    return (len(a) >= 2 and len(b) >= 2
            and not a.isascii() and not b.isascii()
            and bool(set(a) & set(b)))


def _find(parent: dict, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def count_matched_concepts(matched: set) -> int:
    parent = {t: t for t in matched}
    group = list(matched)
    for i, a in enumerate(group):
        for b in group[i + 1:]:
            if not _same_word(a, b):
                continue
            ra, rb = _find(parent, a), _find(parent, b)
            if ra != rb:
                parent[ra] = rb
    return len({_find(parent, t) for t in group})


# ── 检索器 ────────────────────────────────────────────

@dataclass
class _Doc:
    item_id: str
    tokens: list


class RunbookRetriever:
    def __init__(self, items: list,
                 coverage_strong: float = COVERAGE_STRONG,
                 coverage_weak: float = COVERAGE_WEAK,
                 unseen_weight_ratio: float = UNSEEN_WEIGHT_RATIO):
        self._coverage_strong = coverage_strong
        self._coverage_weak = coverage_weak
        self._unseen_ratio = unseen_weight_ratio
        # 去重别名只保留旧检索文档；执行候选始终使用仍在模板库中的编号。
        self._canonical_ids = {alias['id']: item['id'] for item in items
                               for alias in item.get('retrieval_aliases', [])}
        self._docs = self._build_docs(items)
        self._doc_count = len(self._docs)
        self._df = self._build_df()
        self._avg_len = sum(len(d.tokens) for d in self._docs) / max(self._doc_count, 1)
        self._idf = {t: math.log((self._doc_count - d + 0.5) / (d + 0.5) + 1)
                     for t, d in self._df.items()}
        median = sorted(self._idf.values())[len(self._idf) // 2] if self._idf else 0.0
        self._tau = median
        self._unseen_weight = self._tau * self._unseen_ratio
        self._generic_df_limit = GENERIC_DF_RATIO * self._doc_count
        # 文档在索引生命周期内不变，词频只构造一次，避免每次查询重复计数。
        self._doc_tfs = [Counter(doc.tokens) for doc in self._docs]

    @staticmethod
    def _build_docs(items: list) -> list:
        entries = list(items)
        for item in items:
            for alias in item.get('retrieval_aliases', []):
                # 保持原文档顺序、重复次数和 IDF，避免去重同时改变 BM25 权重。
                pos = next(i for i, entry in enumerate(entries)
                           if entry['id'] == alias['after_id']) + 1
                entries.insert(pos, alias)
        docs = []
        for item in entries:
            for example in item.get("examples", []):
                docs.append(_Doc(item["id"], tokenize(example)))
            if item.get("description"):
                docs.append(_Doc(item["id"], tokenize(item["description"])))
        return docs

    def _build_df(self) -> Counter:
        df = Counter()
        for doc in self._docs:
            for token in set(doc.tokens):
                df[token] += 1
        return df

    def _doc_weight(self, token: str) -> float:
        return min(self._idf.get(token, 0.0), self._tau)

    def _query_weight(self, token: str) -> float:
        if token in self._df:
            return min(self._idf[token], self._tau)
        return self._unseen_weight

    def retrieve(self, query: str, top_k: int = None) -> List[Candidate]:
        query_tokens = set(tokenize(query))
        content, denominator = self._coverage_base(query_tokens)
        ranked = self._aggregate_items(query_tokens, content, denominator)
        results = self._assemble_results(ranked)
        if top_k is not None:
            results = results[:top_k]
        unique, seen = [], set()
        for candidate in results:
            item_id = self._canonical_ids.get(candidate.id, candidate.id)
            if item_id not in seen:
                seen.add(item_id)
                unique.append(Candidate(item_id, candidate.tier, candidate.score,
                                        candidate.coverage))
        return unique

    def _is_content_token(self, token: str) -> bool:
        return (self._df.get(token, 0) <= self._generic_df_limit
                and not token.isdigit())

    def _coverage_base(self, query_tokens: set):
        content = [t for t in query_tokens if self._is_content_token(t)]
        denominator = sum(self._query_weight(t) for t in content)
        return content, denominator

    def _aggregate_items(self, query_tokens: set, content: list, denominator: float) -> list:
        items = {}
        for doc, tf in zip(self._docs, self._doc_tfs):
            score = self._bm25_score(query_tokens, tf, len(doc.tokens))
            entry = items.setdefault(doc.item_id, {"score": 0.0, "matched": set()})
            entry["score"] = max(entry["score"], score)
            entry["matched"] |= {t for t in content if tf.get(t)}

        ranked = []
        for item_id, entry in items.items():
            if not entry["matched"]:
                continue
            coverage = (sum(self._query_weight(t) for t in entry["matched"]) / denominator
                        if denominator > 0 else 0.0)
            tier = self._classify(coverage, entry["matched"],
                                  self._coverage_strong, self._coverage_weak)
            if tier:
                ranked.append(Candidate(id=item_id, tier=tier,
                                        score=round(entry["score"], 3),
                                        coverage=round(coverage, 3)))
        ranked.sort(key=lambda c: -c.score)
        return ranked

    def _bm25_score(self, query_tokens: set, tf: Counter, doc_len: int) -> float:
        norm = BM25_K1 * (1 - BM25_B + BM25_B * doc_len / max(self._avg_len, 1))
        return sum(self._doc_weight(t) * tf[t] * (BM25_K1 + 1) / (tf[t] + norm)
                   for t in query_tokens if tf.get(t))

    @staticmethod
    def _classify(coverage: float, matched: set,
                  coverage_strong: float, coverage_weak: float):
        if coverage >= coverage_strong and (
                count_matched_concepts(matched) >= 2 or coverage >= NEAR_FULL_COVERAGE):
            return "strong"
        if coverage >= coverage_weak:
            return "weak"
        return None

    @staticmethod
    def _assemble_results(ranked: list) -> list:
        strong = [c for c in ranked if c.tier == "strong"]
        if strong:
            top = strong[0]
            kept = [top] + [c for c in strong[1:]
                            if c.score >= STRONG_SCORE_MARGIN * top.score]
            kept = kept[:MAX_STRONG_RESULTS]
            # Also include weak candidates so LLM has more choices
            weak = [c for c in ranked if c.tier == "weak"][:MAX_WEAK_RESULTS]
            return kept + weak
        return ranked[:MAX_WEAK_RESULTS]
