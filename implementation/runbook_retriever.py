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


"""Text-only explicit output-field views; no execution or semantic adapter calls."""
def _attribute_literal_mask(text):
    pairs={'"':'"',"'":"'",'“':'”','‘':'’'};chars=list(text);i=0
    while i<len(text):
        if text[i] not in pairs:i+=1;continue
        quote=pairs[text[i]];j=i+1
        while j<len(text):
            if text[j]=='\\':j+=2;continue
            if text[j]==quote:break
            j+=1
        if j==len(text):return None
        chars[i:j+1]=' '*(j+1-i);i=j+1
    return ''.join(chars)

def _attribute_intent(query):
    marker=re.search(r'(?:输出|返回(?:字段)?|展示字段|列出字段|保留字段|选择字段|SELECT)\s*[:：]?\s*(.+?)\s*[。.]?\s*$',query,re.I)
    if not marker:return None
    raw=marker.group(1).strip(' 。.')
    if not re.fullmatch(r'''[A-Za-z0-9_\s、,，;；|\[\]`"']+''',raw):return None
    projection=tuple(x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]*',raw))
    if not projection or len(set(projection))!=len(projection):return None
    prefix=_attribute_literal_mask(query[:marker.start()])
    if prefix is None or re.search(r'或|不是|不等于|包含|开头|(?<![A-Za-z])(?:OR|NOT)(?![A-Za-z])',prefix,re.I):return None
    filters={x.lower() for x in re.findall(r'(?<![A-Za-z0-9_.])([A-Za-z][A-Za-z0-9_]*)\s*=',prefix)}
    for field,pattern in [('name',r'名称|名字|实例名'),('tenantName',r'租户(?:名称)?'),('logicalRegionName',r'逻辑区域|区域'),('azoneName',r'可用区'),('status',r'状态'),('vdcName',r'VDC(?:名称)?')]:
        if re.search(r'(?:'+pattern+r')\s*(?:为|是|=)',prefix,re.I):filters.add(field.lower())
    return dict(prefix=prefix,projection=projection,filters=frozenset(filters))

def _attribute_resource_match(term,text):
    if term.isascii():return bool(re.search(r'(?<![A-Za-z0-9_])'+re.escape(term)+r'(?![A-Za-z0-9_])',text,re.I))
    return term in text


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
        for item in items:
            for view in item.get('retrieval_views', []):
                prior = self._canonical_ids.get(view['id'])
                if prior is not None and prior != item['id']:
                    raise ValueError('retrieval view and alias owner conflict')
                self._canonical_ids[view['id']] = item['id']
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
        self._build_attribute_index(items)

    @staticmethod
    def _build_docs(items: list) -> list:
        if any('retrieval_views' in item for item in items):
            # Views contain retrieval text only. Display/API/SQL remain on active items.
            # Preserve separate profile scores/coverage until the existing final ID map.
            entries, pending = [], []
            explicit_views = {view['id']: (item['id'], view)
                              for item in items for view in item.get('retrieval_views', [])}
            allowed = {'id', 'after_id', 'description', 'examples', 'description_repeat'}
            for item in items:
                views = item.get('retrieval_views')
                if views is not None:
                    if not isinstance(views, list) or not views:
                        raise ValueError('retrieval_views must be a nonempty text list')
                    for view in views:
                        if (not isinstance(view, dict) or set(view) - allowed
                                or not isinstance(view.get('id'), str)
                                or not view['id']
                                or not isinstance(view.get('description', ''), str)
                                or not isinstance(view.get('examples', []), list)
                                or any(not isinstance(x, str) for x in view.get('examples', []))
                                or view.get('after_id') is not None and not isinstance(view['after_id'], str)
                                or not isinstance(view.get('description_repeat', 1), int)
                                or isinstance(view.get('description_repeat', 1), bool)
                                or not 1 <= view.get('description_repeat', 1) <= 4):
                            raise ValueError('invalid retrieval text view')
                    entries.append(views[0])
                    pending.extend(views[1:])
                else:
                    entries.append(item)
                for alias in item.get('retrieval_aliases', []):
                    explicit = explicit_views.get(alias['id'])
                    if explicit is None:
                        pending.append(alias)
                        continue
                    owner, view = explicit
                    alias_texts = alias.get('examples', []) + ([alias['description']] if alias.get('description') else [])
                    view_texts = view.get('examples', []) + ([view['description']] * view.get('description_repeat', 1) if view.get('description') else [])
                    if (owner != item['id'] or alias_texts != view_texts
                            or set(alias) - {'id', 'after_id', 'description', 'examples'}):
                        raise ValueError('legacy alias and explicit view text conflict')
                    # Keep the migrated alias metadata, but index its exact text only
                    # through the explicit profile. Never count the same text twice.
            all_ids = [entry['id'] for entry in entries + pending]
            if len(all_ids) != len(set(all_ids)):
                raise ValueError('duplicate retrieval text view ID')
            # Resolve anchors globally; a legacy alias may depend on another family's
            # pending view (054 after053). Missing/cyclic anchors fail explicitly.
            while pending:
                remaining = []
                for view in pending:
                    position = next((i for i, entry in enumerate(entries)
                                     if entry['id'] == view.get('after_id')), None)
                    if position is None:
                        remaining.append(view)
                    else:
                        entries.insert(position + 1, view)
                if len(remaining) == len(pending):
                    raise ValueError('missing or cyclic retrieval view anchor')
                pending = remaining
            # Bootstrap views keep active-item positions; validate their declared
            # anchors too, instead of silently ignoring missing/backward cycles.
            positions = {entry['id']: i for i, entry in enumerate(entries)}
            for entry in entries:
                anchor = entry.get('after_id')
                if anchor is not None and (anchor not in positions
                        or positions[anchor] >= positions[entry['id']]):
                    raise ValueError('invalid initial retrieval view anchor')
            docs = []
            for entry in entries:
                for example in entry.get('examples', []):
                    docs.append(_Doc(entry['id'], tokenize(example)))
                if entry.get('description'):
                    for _ in range(entry.get('description_repeat', 1)):
                        docs.append(_Doc(entry['id'], tokenize(entry['description'])))
            return docs
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

    def _build_attribute_index(self,items):
        records={};cards=[]
        for item in items:
            metadata=item.get('retrieval_attributes')
            if metadata is None:continue
            if set(metadata)!={'resource_terms','views'} or not isinstance(metadata['resource_terms'],str) or not isinstance(metadata['views'],list):raise ValueError('invalid retrieval_attributes')
            terms=tuple(metadata['resource_terms'].split())
            if not terms:raise ValueError('empty attribute resource terms')
            for view in metadata['views']:
                if set(view)!={'output','filters'} or not all(isinstance(view[k],str) for k in ['output','filters']):raise ValueError('invalid attribute view')
                projection=tuple(view['output'].lower().split())
                for filter_text in view['filters'].split('|'):
                    filters=frozenset(filter_text.lower().split());key='attribute_text_'+str(len(cards))
                    records[key]=dict(owner=item['id'],projection=projection,filters=filters,resource_terms=terms)
                    cards.append(dict(id=key,description='查询 '+metadata['resource_terms']+' 筛选 '+filter_text+' 输出 '+view['output']))
        self._attribute_records=records
        self._attribute_index=RunbookRetriever(cards,self._coverage_strong,self._coverage_weak,self._unseen_ratio) if cards else None

    def _attribute_candidates(self,query):
        if self._attribute_index is None:return []
        intent=_attribute_intent(query)
        if intent is None:return []
        matched={record['resource_terms'] for record in self._attribute_records.values() if any(_attribute_resource_match(term,intent['prefix']) for term in record['resource_terms'])}
        if len(matched)!=1:return []
        resource_terms=next(iter(matched));resource=next(term for term in resource_terms if _attribute_resource_match(term,intent['prefix']))
        normalized='查询 '+resource+' 筛选 '+' '.join(sorted(intent['filters']))+' 输出 '+' '.join(intent['projection'])
        candidates=self._attribute_index._retrieve_primary(normalized)
        result=[];seen=set()
        for candidate in candidates:
            record=self._attribute_records[candidate.id]
            if candidate.tier!='strong' or record['resource_terms']!=resource_terms or record['projection']!=intent['projection'] or record['filters']!=intent['filters']:continue
            if record['owner'] not in seen:
                result.append(Candidate(record['owner'],candidate.tier,candidate.score,candidate.coverage));seen.add(record['owner'])
        return result

    def retrieve(self,query: str,top_k: int=None)->List[Candidate]:
        attributes=self._attribute_candidates(query)
        if not attributes:return self._retrieve_primary(query,top_k)
        primary=self._retrieve_primary(query)
        original={candidate.id:candidate for candidate in primary};seen=set();merged=[]
        for candidate in attributes+primary:
            if candidate.id not in seen:
                merged.append(original.get(candidate.id,candidate));seen.add(candidate.id)
        return merged if top_k is None else merged[:top_k]

    def _retrieve_primary(self, query: str, top_k: int = None) -> List[Candidate]:
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
