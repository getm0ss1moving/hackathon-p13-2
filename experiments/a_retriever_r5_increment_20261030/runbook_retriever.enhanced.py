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
    profile_ids: tuple = ()  # compound source views; empty on single requests
    obligation_spans: tuple = ()  # (start, end, source-profile IDs) per obligation


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
    visible = _attribute_literal_mask(query)
    if visible is None:
        return None
    # Markers are searched only outside complete quoted literals. Projection text
    # is read from the original suffix, so quoted field identifiers still work.
    markers = list(re.finditer(
        r'输出|返回(?:字段)?|展示字段|列出字段|保留字段|选择字段|(?<![A-Za-z0-9_])SELECT(?![A-Za-z0-9_])',
        visible, re.I))
    for marker in reversed(markers):
        raw = query[marker.end():].lstrip(' \t\n:：').rstrip(' 。.\t\n')
        if not re.fullmatch(r'''[A-Za-z0-9_\s、,，;；|\[\]`"']+''', raw):
            continue
        projection = tuple(x.lower() for x in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', raw))
        if not projection or len(set(projection)) != len(projection):
            continue
        prefix = visible[:marker.start()]
        if re.search(r'或|不是|不等于|开头|(?<![A-Za-z])(?:OR|NOT)(?![A-Za-z])', prefix, re.I):
            return None
        contains = list(re.finditer('包含', prefix))
        if contains:
            # This is an index hint for the existing ELB name-contain contract;
            # no API operator or executor decision is constructed here.
            is_elb = any(_attribute_resource_match(term, prefix)
                         for term in ('ELB', 'CLOUD_ELB', '负载均衡'))
            name_contains = [m.span() for m in re.finditer(
                r'(?:名称|名字|实例名|(?<![A-Za-z0-9_])name(?![A-Za-z0-9_]))\s*包含', prefix, re.I)]
            if not is_elb or any(not any(a <= m.start() and m.end() <= b for a,b in name_contains) for m in contains):
                return None
        filters = {x.lower() for x in re.findall(
            r'(?<![A-Za-z0-9_.])([A-Za-z][A-Za-z0-9_]*)\s*(?:等于|为|是|=)', prefix)}
        roles = [('name',r'名称|名字|实例名'),('tenantName',r'租户(?:名称)?'),
                 ('logicalRegionName',r'逻辑区域|区域'),('azoneName',r'可用区'),
                 ('status',r'状态'),('vdcName',r'VDC(?:名称)?')]
        for field,pattern in roles:
            if re.search(r'(?:'+pattern+r')\s*(?:等于|为|是|=)', prefix, re.I):
                filters.add(field.lower())
        if contains:
            filters.add('name')
        return dict(prefix=prefix,projection=projection,filters=frozenset(filters))
    return None

def _attribute_resource_match(term,text):
    if term.isascii():return bool(re.search(r'(?<![A-Za-z0-9_])'+re.escape(term)+r'(?![A-Za-z0-9_])',text,re.I))
    return term in text


# Explicit independent requests only; quoted names/values never split or veto.
MAX_COMPOUND_CLAUSES = 4
MAX_OBLIGATION_PROFILES = MAX_STRONG_RESULTS
MAX_COMPOUND_PROFILES = MAX_STRONG_RESULTS + MAX_WEAK_RESULTS
_REQUEST_VERB = r"(?:请\s*|帮我\s*|麻烦\s*)?(?:查询|统计|列出|计算|输出|返回|删除|重建|更新|修改|预测|show\b|list\b|count\b)"
_CLAUSE_BREAK = re.compile(
    r"[；;。]\s*(?:同时|另外|并且|以及|再|还请)\s*[,，:：]?\s*"
    r"|(?:[；;。]\s*|[,，]\s*(?:同时|另外|并且|还请)\s*[,，:：]?\s*"
    r"|(?:同时|另外|并且|以及|并)\s*[,，:：]?\s*)(?=" + _REQUEST_VERB + r")", re.I)
# These are semantic request categories, never entity IDs or question matches.
# A term only vetoes when the template corpus has no corresponding capability.
_CAPABILITY_OBJECTIVES = (
    "预测", "预报", "概率", "评分", "温度", "功耗", "电压", "电流", "转速",
    "forecast", "predict", "probability", "temperature", "wattage", "voltage")
_WRITE_REQUEST = re.compile(
    r"^(?:请|帮我|麻烦|立即|批量|全部|先|再|同时|另外|并且|\s)*"
    r"(?:删除|重建|更新|修改|创建|新增|重启|启动|关闭|迁移|扩容|缩容|清空|"
    r"delete\b|rebuild\b|update\b|create\b|restart\b)", re.I)


def _compound_parts(query, merge_aggregation=True):
    visible = _intent_literal_mask(query)
    if visible is None:return None
    markers=list(_CLAUSE_BREAK.finditer(visible))
    parts=[];start=0
    for n,marker in enumerate(markers):
        end=markers[n+1].start() if n+1<len(markers) else len(query)
        left=query[start:marker.start()].strip()
        right=query[marker.end():end].strip()
        if merge_aggregation and left and _aggregation_continuation(left,right,marker.group()):
            continue
        if left:parts.append((start,marker.start(),left))
        start=marker.end()
    if query[start:].strip():parts.append((start,len(query),query[start:].strip()))
    return parts if 1<=len(parts)<=MAX_COMPOUND_CLAUSES else None


# Intents are bounded against actual native fields, never a resource blacklist.
# Normal static properties (createdAt, protocol, engineVersion, size, usage_rate)
# remain queryable. A category only abstains when its required schema is absent.
_METRIC_BOUNDARIES = (
    ('latency', r'耗时|时延|延迟|响应时间|用时|用多久|花多久|(?<![a-z0-9_.-])(?:latency|duration)(?![a-z0-9_.-])',
     r'latency|duration|elapsed|responsetime|handshaketime'),
    ('operation_rate', r'(?<![a-z0-9_.-])(?:iops|qps|tps)(?![a-z0-9_.-])|吞吐(?:量|率)?|每秒.{0,8}(?:读|写|请求)',
     r'iops|qps|tps|throughput|operationspersecond|requestspersecond|readrate|writerate'),
    ('financial', r'采购|折旧|成本|费用|价格|账单|支出|开销|资费|折价|账面|估值|价值|(?:花|付)(?:费)?(?:多少|几)?[钱元]|(?:多少|几)[钱元]|(?<![a-z0-9_.-])(?:cost|price|depreciation|billing)(?![a-z0-9_.-])',
     r'cost|price|deprecia|purchase|billing|expense'),
    ('quantile', r'分位(?:数|值)?|(?<![a-z0-9_.-])(?:p(?:[1-9][0-9]?|100)|percentile|quantile)(?![a-z0-9_.-])',
     r'percentile|quantile|^p(?:[1-9][0-9]?|100)'),
)
_METRIC_BOUNDARIES += (
    ('operation_measure',r'(?:(?:每次|单次)(?:读取?|写入?|请求|操作)|(?:读取?|写入?)请求).{0,16}(?:次数|数量|字节|大小|耗时|用时|延迟|时间)',
     r'read_?count|write_?count|request_?count|operation_?count|read_?bytes|write_?bytes|bytesperrequest'),
)
_METRIC_BOUNDARIES = tuple((name,re.compile(intent,re.I),re.compile(field,re.I))
                           for name,intent,field in _METRIC_BOUNDARIES)
_MUTATION_TARGET = re.compile(
    r'(?:把|将|给|为)[^；;。!?]*?(?:升级|降级|重启|扩容|缩容|删除|重建|更新|修改|关闭|迁移|清空)',re.I)
_MUTATION_HEAD = re.compile(r'^(?:请|帮我|麻烦|立即|批量|全部|先|再|\s)*(?:升级|降级|upgrade\b|downgrade\b)',re.I)
_READ_HEAD = re.compile(r'^(?:请|帮我|麻烦|\s)*(?:查询|统计|列出|计算|显示|展示|返回|输出)',re.I)
_TIME_SERIES_SCOPE = re.compile(
    r'(?:历史|过去|最近|近[一二三四五六七八九十0-9]+[天日周月年]).{0,36}(?:变化|趋势|曲线|采样|监测|序列|分位)'
    r'|(?:未来|下一?个?)[一二三四五六七八九十0-9]*[天日周月年季度]'
    r'|(?:按|逐|每)(?:分钟|小时|天|日|月|年)|趋势|曲线|(?:状态|配置|数量|容量)(?:的)?变化',re.I)
_TIME_SERIES_FIELD = re.compile(r'observed|sampled|sampletime|timestamp|history|historical|metrictime|timeseries',re.I)


def _native_schema(item):
    fields=set();methods=set()
    def visit(value,key=''):
        if isinstance(value,dict):
            for name,child in value.items():
                if name=='method' and isinstance(child,str):methods.add(child.upper())
                if name=='simple' and isinstance(child,dict) and isinstance(child.get('name'),str):fields.add(child['name'])
                visit(child,name)
        elif isinstance(value,list):
            for child in value:visit(child,key)
        elif isinstance(value,str) and key in {
                'sql','sql_template','output','columns','ordered_columns','output_columns','output_fields'}:
            fields.update(re.findall(r'[A-Za-z_][A-Za-z0-9_]*',value))
    visit(item)
    return frozenset(fields),frozenset(methods)



# Grammar delimiters for entity roles, not a resource exclusion list. A resource
# followed by an object name and an attribute request retains its resource/goal;
# metric/action words inside the object value are never promoted to obligations.
_RESOURCE_NOUN = r'(?:VM_NOVA|GAUSSDB_INSTANCE|ECS|GaussDB|ELB|VPC|RDS|虚拟机|云主机|宿主机|物理服务器|物理机|负载均衡|监听器|云硬盘|云盘|磁盘|存储池|数据库|集群|应用|子网|端口|安全组)'
_ENTITY_ATTRIBUTE = re.compile(
    r'(?<![A-Za-z0-9_])'+_RESOURCE_NOUN+r'\s*(?P<value>[^的，,；;。!?\n=]+?)的',re.I)
_NAME_VALUE = re.compile(
    r'(?:(?:\bname|名称|名字|实例名)\s*(?:=|为|是)|名为|叫做)\s*(?P<value>[^的，,；;。!?\n]+)',re.I)
_STATIC_PROPERTY_HEAD = re.compile(
    r'^\s*(?:创建时间|创建日期|状态|规格|名称|IP|网卡|镜像|操作系统|CPU型号|CPU架构|createdAt|status|flavorCode|privateIps|cpuModel|cpuArch)',re.I)
_NOT_ENTITY_BODY = re.compile(r'^(?:实例)?(?:中|内|下|按|使用|每|所有|各)|按|统计|分布|使用最多|每秒|每次')
_ENTITY_RELATION_SUFFIX = re.compile(r'(?:关联|使用|挂载|所属|属于|位于|所在|包含|对应|部署|运行|创建|绑定|实例中|实例下|上|下)$')
_MUTATION_VERB = r'(?:删除|重建|更新|修改|创建|新增|重启|启动|关闭|迁移|扩容|缩容|清空|升级|降级|开机|关机|delete\b|rebuild\b|update\b|create\b|restart\b|upgrade\b|downgrade\b|shutdown\b)'
_MUTATION_TARGET = re.compile(r'(?:把|将|给|为)[^；;。!?]*?'+_MUTATION_VERB,re.I)
_COMMAND_BREAK = re.compile(
    r'[,，;；。]\s*(?:(?:然后|随后|接着|再|并且|并|且|同时|另外|还要|以及|顺便)\s*)?'
    r'|(?:然后|随后|接着)\s*'
    r'|(?:并且|并|且|再|同时|另外|还要|以及|顺便)\s*(?=(?:把|将|给|为|'+_MUTATION_VERB+r'))',re.I)
_COMMAND_PREFIX = re.compile(r'^(?:请|帮我|麻烦|立即|批量|全部|先|再|然后|随后|接着|并且|并|且|同时|另外|还要|以及|顺便|\s)*',re.I)
# Sequenced read requests also retain independent source-profile obligations.
_CLAUSE_BREAK = re.compile(_CLAUSE_BREAK.pattern +
    r'|[,，;；。]\s*(?:然后|随后|接着|再)\s*[,，:：]?\s*'
    r'|(?:然后|随后|接着)\s*',re.I)


def _intent_literal_mask(query):
    visible = _attribute_literal_mask(query)
    if visible is None:return None
    chars=list(visible)
    # Explicit/quoted names win over apparent connectives within their values.
    for match in _NAME_VALUE.finditer(visible):
        start,end=match.span('value');chars[start:end]=' '*(end-start)
    named=''.join(chars);cuts=[0]
    for marker in _INDEPENDENT_REQUEST.finditer(named):
        if _COMPLETE_READ_TARGET.search(named[cuts[-1]:marker.start()]):
            cuts.append(marker.end())
    cuts.append(len(named))
    # NP values are matched inside a proven request scope, never across a new
    # read-verb + resource request. This also preserves the RHS entity masking.
    for start,end in zip(cuts,cuts[1:]):
        fragment=named[start:end]
        for match in _ENTITY_ATTRIBUTE.finditer(fragment):
            a,b=match.span('value');value=fragment[a:b]
            if (_NOT_ENTITY_BODY.search(value.strip())
                    and not _STATIC_PROPERTY_HEAD.match(fragment[match.end():])):continue
            suffix=_ENTITY_RELATION_SUFFIX.search(value)
            if suffix:b=a+suffix.start()
            chars[start+a:start+b]=' '*(b-a)
    return ''.join(chars)


# One grammar supplies BOTH command boundaries and leading normalization. These
# are discourse/politeness roles, never query/entity matches. Entity values have
# already been masked before any of these functions are called.
_DISCOURSE_CLASSES = {
    'contrast':r'但是|但|不过|然而|可是|只是',
    'sequence':r'接下来|下一步|之后|然后|随后|接着|继而',
    'addition':r'另外|此外|同时|并且|而且|还要|以及|顺便',
}
_DISCOURSE_MARKER = '(?:'+'|'.join(_DISCOURSE_CLASSES.values())+')'
_POLITE_MARKER = r'(?:请问|烦请|劳烦|劳驾|麻烦(?:你|您)?(?:帮我)?|请(?:你|您)?(?:帮我)?|帮我|替我|能否|可否|是否可以|可以(?:请)?(?:你|您)?)'
_COMMAND_ADVERB = r'(?:务必|直接|立刻|立即|现在|马上|先|再|批量|全部|尽快|顺手|仅仅|仅|只|不仅|不但|不光)'
_COMMAND_LEADING = re.compile(
    r'^\s*(?:(?:'+_DISCOURSE_MARKER+'|'+_POLITE_MARKER+'|'+_COMMAND_ADVERB+r')\s*[,，:：]?\s*)+',re.I)
# Negation is local to one command, never a whole-query exemption. Contrast and
# sequencing end that scope. Affirmative commands after them are still checked.
_NEGATED_COMMAND = re.compile(r'^(?:绝不|切勿|不要|禁止|无需|无须|不必|不用|不许|不得|不能|别|勿|不(?!仅|但|止|光))',re.I)
_COMMAND_BREAK = re.compile(_COMMAND_BREAK.pattern+'|'+_DISCOURSE_MARKER+r'\s*',re.I)


def _normalise_command(command):
    return _COMMAND_LEADING.sub('',command).strip()


_NEGATION_IN_SCOPE = re.compile(_NEGATED_COMMAND.pattern.lstrip('^'),re.I)
_AFFIRMATIVE_MODAL = re.compile(r'不妨|何不|不如|不得不|不能不|不是不|并非不')


def _scope_negates(prefix):
    # Proposal and double-negative operators are affirmative; a remaining
    # explicit negation still applies only to this command's action prefix.
    return bool(_NEGATION_IN_SCOPE.search(_AFFIRMATIVE_MODAL.sub('',prefix)))

_READ_FRAME = re.compile(r'查询|统计|列出|计算|显示|展示|返回|输出|查看|查找|看看',re.I)
_NATIVE_PREDICATE = re.compile(r'可启动')  # existing native bootable field, not a launch imperative


def _command_requests_mutation(command):
    command = _normalise_command(command)
    if not command:
        return False
    # The object of 把/将/给/为 is inside the action scope. A negative word in
    # that object must not negate the command; inspect only before the target.
    for target in _MUTATION_TARGET.finditer(command):
        verbs = list(re.finditer(_MUTATION_VERB,target.group(),re.I))
        verb_start = target.start()+verbs[-1].start()
        verb_end = target.start()+verbs[-1].end()
        if (_STATIC_PROPERTY_HEAD.match(command[verb_start:])
                or re.match(r'(?:时间|日期|状态|记录|历史|字段|次数)',command[verb_end:])):
            continue
        if not _scope_negates(command[:target.start()]):
            return True
    read_frame = _READ_FRAME.search(command)
    # Recover free imperatives after non-enumerated polite/adverbial material.
    # Native projection nouns remain nouns, even in an unheaded field fragment.
    for verb in re.finditer(_MUTATION_VERB,command,re.I):
        suffix = command[verb.start():]
        after = command[verb.end():]
        if ((read_frame is not None and read_frame.start()<verb.start())
                or any(p.start()<=verb.start() and verb.end()<=p.end() for p in _NATIVE_PREDICATE.finditer(command))
                or _STATIC_PROPERTY_HEAD.match(suffix)
                or re.match(r'(?:时间|日期|状态|记录|历史|字段|次数)',after)):
            continue
        if not _scope_negates(command[:verb.start()]):
            return True
    return False



# Split only explicit requests after AND, with ASCII boundaries; entity values
# are protected first. Group-count continuations are adjudicated separately.
_CLAUSE_BREAK = re.compile(_CLAUSE_BREAK.pattern +
    r'|(?:[,，]\s*)?(?<![A-Za-z0-9_.-])AND(?![A-Za-z0-9_.-])\s*[,，:：]?\s*(?='+_REQUEST_VERB+r')',re.I)
_INDEPENDENT_REQUEST = re.compile(
    r'(?:并且|以及|同时|并|(?<![A-Za-z0-9_.-])AND(?![A-Za-z0-9_.-]))\s*[,，:：]?\s*'
    r'(?='+_REQUEST_VERB+r'\s*'+_RESOURCE_NOUN+r')',re.I)
_COMPLETE_READ_TARGET = re.compile(
    r'(?:架构(?:类型|分布|统计)?|类型(?:分布|统计)?|状态(?:分布|统计)?|协议(?:分布|统计)?|版本(?:分布|统计)?|创建时间|规格|数量|IP|列表)\s*[,，]?\s*$',re.I)
_GROUP_AXES = (
    ('architecture',r'架构|cpuArch'),('status',r'状态|status'),
    ('protocol',r'协议|protocol'),('version',r'版本|engineVersion'),
    ('os',r'操作系统|osType'),('tenant',r'租户|tenant'),('zone',r'可用区|azone'),
)
_GROUP_AXES = tuple((axis,re.compile(pattern,re.I)) for axis,pattern in _GROUP_AXES)
_GENERIC_GROUP = re.compile(r'类型|种类|类别')
_ROW_OUTPUT = re.compile(r'每台|逐台|逐个|每个实例|明细|详情|详细|名称|名字|编号|(?<![A-Za-z])(?:IP|ID)(?![A-Za-z])',re.I)
_COUNT_CONTINUATION = re.compile(
    r'^\s*(?:请\s*)?(?:统计|计算|计数|查询|列出|展示|给出|返回|输出)\s*'
    r'(?P<group>各类(?:型)?|每类(?:型)?|各(?:种|个)?(?:CPU)?(?:架构|状态|协议|版本|类型|种类|类别)|每(?:种|个)?(?:CPU)?(?:架构|状态|协议|版本|类型|种类|类别))'
    r'\s*(?:的)?\s*(?:数量|台数|数目|个数|计数|count)\s*[。.!]?\s*$',re.I)


def _group_axis(text):
    axes={axis for axis,pattern in _GROUP_AXES if pattern.search(text)}
    if len(axes)>1:return None
    return next(iter(axes)) if axes else 'type' if _GENERIC_GROUP.search(text) else None


def _aggregation_continuation(left,right,connector):
    # A strong separator, new resource/scope/value, or row-detail projection is
    # never folded just because the following verb happens to be 'statistics'.
    if re.search(r'[；;。]|然后|随后|接着|下一步|再',connector):return False
    lhs=_intent_literal_mask(left)
    if lhs is None or not re.search(_RESOURCE_NOUN,lhs,re.I) or _ROW_OUTPUT.search(lhs):return False
    axis=_group_axis(lhs)
    if axis is None:return False
    if re.search(_MUTATION_VERB,lhs,re.I):return False
    if re.search(_RESOURCE_NOUN,right,re.I) or re.search(r'[="“”\'‘’]|区域|可用区|筛选|条件|限定',right,re.I):return False
    match=_COUNT_CONTINUATION.fullmatch(right.strip(' ，,'))
    if match is None:return False
    right_axis=_group_axis(match['group'])
    return right_axis in (None,'type',axis)


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
        self._build_intent_index(items)

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

    def _build_intent_index(self, items):
        self._native_fields = {}
        methods = set()
        for item in items:
            fields, native_methods = _native_schema(item)
            self._native_fields[item['id']] = fields
            methods.update(native_methods)
        self._read_only_catalog = not methods - {'GET','HEAD'}

    def _intent_outside_contract(self, visible, parts):
        if self._read_only_catalog:
            for _,_,clause in parts:
                visible_clause = _intent_literal_mask(clause) or ''
                # Read syntax in one command never exempts subsequent commands.
                # Quoted and unquoted object values are masked before splitting.
                for command in _COMMAND_BREAK.split(visible_clause):
                    if _command_requests_mutation(command):
                        return True
        requested = [(name,field) for name,intent,field in _METRIC_BOUNDARIES
                     if intent.search(visible)]
        temporal = bool(_TIME_SERIES_SCOPE.search(visible))
        if not requested and not temporal:
            return False
        # Only fields declared by lexically relevant native templates count;
        # incidental terms in examples or a different resource do not grant API.
        owners = {self._canonical_ids.get(c.id,c.id)
                  for c in self._single_profiles(visible)}
        fields = {field for owner in owners for field in self._native_fields.get(owner,())}
        if any(not any(pattern.search(field) for field in fields)
               for _,pattern in requested):
            return True
        return temporal and not any(_TIME_SERIES_FIELD.search(field) for field in fields)

    def _unsupported_request(self, query):
        visible = _intent_literal_mask(query)
        if visible is None:
            return True
        text = visible.lower()
        if re.search(r"不要(?:查询|统计)|无需(?:查询|统计)", text):
            return True
        # The current contract is a read-only resource catalog. Questions about
        # historical deleted resources do not start with an imperative write.
        parts = _compound_parts(query)
        if parts is None:
            return True
        if any(_WRITE_REQUEST.search(part[2]) for part in parts):
            return True
        if self._intent_outside_contract(text, parts):
            return True
        for term in _CAPABILITY_OBJECTIVES:
            present = (bool(re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(term) + r"(?![A-Za-z0-9_.-])", text))
                       if term.isascii() else term in text)
            if present and not set(tokenize(term)) <= self._df.keys():
                return True
        return False

    def _single_profiles(self, query):
        tokens = set(tokenize(query))
        content, denominator = self._coverage_base(tokens)
        return self._assemble_results(self._aggregate_items(tokens, content, denominator))

    def retrieve_obligations(self, query):
        """Bounded clause evidence; spans preserve same-view different entities.

        This is retrieval evidence, not parameter extraction or execution proof.
        No recognized/strong candidate for any clause means full abstention.
        """
        if self._unsupported_request(query):
            return []
        parts = _compound_parts(query)
        if parts is None or len(parts) < 2:
            return []
        evidence = []
        for start, end, text in parts:
            # Quoted entity values do not describe requested capabilities and
            # must not dilute a clause's coverage. Keep the original span/text.
            lexical = _intent_literal_mask(text)
            strong = [c for c in self._atomic_profiles(lexical) if c.tier == "strong"]
            if not strong:
                return []
            evidence.append(dict(start=start, end=end, text=text,
                                 candidates=strong[:MAX_OBLIGATION_PROFILES]))
        required = {c.id for obligation in evidence for c in obligation['candidates']}
        if len(required) > MAX_COMPOUND_PROFILES:
            return []
        return evidence

    def _atomic_profiles(self, query, top_k=None, base_profiles=None):
        """One atomic goal can use bounded local BM25 views for recall."""
        original = self._single_profiles(query) if base_profiles is None else base_profiles
        views = _compound_parts(query, merge_aggregation=False)
        if views is None or len(views) < 2:
            return original if top_k is None else original[:top_k]
        seeds = [c for _,_,text in views
                 for c in self._single_profiles(_intent_literal_mask(text))
                 if c.tier == 'strong']
        order=[];best={}
        for candidate in seeds+original:
            if candidate.id not in best:order.append(candidate.id)
            prior=best.get(candidate.id)
            if prior is None or (candidate.tier=='strong',candidate.score)>(prior.tier=='strong',prior.score):
                best[candidate.id]=candidate
        result=[best[identifier] for identifier in order][:MAX_COMPOUND_PROFILES]
        return result if top_k is None else result[:top_k]

    def _retrieve_profile_bundle(self, query, top_k=None):
        """Expose original profiles before canonical family deduplication.

        Single requests retain the exact original BM25 path. Compound requests
        reserve each clause's existing strong profiles (at most five). Abstain
        if their union exceeds 15; otherwise fill from whole-query candidates
        within the existing 15-profile ceiling. No full-index union.
        """
        if self._unsupported_request(query):
            return [], []
        parts = _compound_parts(query)
        if parts is None:
            return [], []
        original = self._single_profiles(query)
        if len(parts) == 1:
            original_by_id = {c.id:c for c in original}
            supported = self._atomic_profiles(query,top_k,base_profiles=original)
            # Public scores retain whole-query provenance when available.
            return [original_by_id.get(c.id,c) for c in supported], []
        obligations = self.retrieve_obligations(query)
        if not obligations:
            return [], []
        original_by_id = {c.id: c for c in original}
        merged, seen = [], set()
        # Reserve clause evidence before optional whole-query fallback. Original
        # scores remain original; a newly exposed view keeps its clause score.
        for candidate in [c for o in obligations for c in o['candidates']] + original:
            if candidate.id not in seen:
                merged.append(original_by_id.get(candidate.id, candidate))
                seen.add(candidate.id)
        merged = merged[:MAX_COMPOUND_PROFILES]
        return (merged if top_k is None else merged[:top_k]), obligations

    def retrieve_profiles(self, query, top_k=None):
        """Source-profile evidence before canonical owner deduplication."""
        return self._retrieve_profile_bundle(query, top_k)[0]

    def retrieve(self,query: str,top_k: int=None)->List[Candidate]:
        if self._unsupported_request(query):return []
        parts = _compound_parts(query)
        if parts is not None and len(parts) > 1:return self._retrieve_primary(query,top_k)
        attributes=self._attribute_candidates(query)
        if not attributes:return self._retrieve_primary(query,top_k)
        primary=self._retrieve_primary(query)
        original={candidate.id:candidate for candidate in primary};seen=set();merged=[]
        for candidate in attributes+primary:
            if candidate.id not in seen:
                merged.append(original.get(candidate.id,candidate));seen.add(candidate.id)
        return merged if top_k is None else merged[:top_k]

    def _retrieve_primary(self, query: str, top_k: int = None) -> List[Candidate]:
        results, obligations = self._retrieve_profile_bundle(query, top_k)
        unique, seen = [], set()
        for candidate in results:
            item_id = self._canonical_ids.get(candidate.id, candidate.id)
            if item_id not in seen:
                seen.add(item_id)
                owned_results = [c for c in results
                                 if self._canonical_ids.get(c.id,c.id)==item_id]
                candidate = max(owned_results,key=lambda c:(c.tier=='strong',c.score))
                profiles = tuple(c.id for c in owned_results) if obligations else ()
                spans = []
                for obligation in obligations:
                    owned = tuple(c.id for c in obligation['candidates'] if c.id in profiles)
                    if owned:spans.append((obligation['start'],obligation['end'],owned))
                unique.append(Candidate(item_id, candidate.tier, candidate.score,
                                        candidate.coverage, profiles, tuple(spans)))
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
