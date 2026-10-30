"""从冻结132记录生成逐题TXT及A交接正文；只读分析，不调用模型、服务或评分器。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'reports/a132_runtime_port_20261030'
CLASSIFICATION = ROOT/'experiments/a132_error_triage_20261031/CLASSIFICATION.json'
ITERATIONS = ['parameter_recovery_fail10', 'parameter_recovery_tail4', 'view_recovery_053',
              'passed_regression4', 'format_recovery_052']
ORDER = ['A_TEMPLATE', 'A_EVIDENCE', 'B_INTEGRATE', 'B_ONLY', 'B_FIXED', 'C_REVIEW']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def compact(value, limit=700):
    text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return text if len(text) <= limit else text[:limit]+'……[仅此证据摘要截取，原题不截取]'


def api_summary(value):
    calls = value if isinstance(value, list) else [value]
    return [{'CI': str(call.get('url', '')).split('?')[0].rsplit('/', 1)[-1],
             '条件': [r.get('simple', r) for r in call.get('condition', {}).get('constraint', [])]}
            for call in calls if isinstance(call, dict)]


def grade(row):
    score = row['score_without_time_penalty']
    return '满分' if score == 5 else '0分' if score == 0 else '错误' if score < 0 else '部分正确'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT/args.output).resolve()
    evidence = (ROOT/args.evidence_dir).resolve()
    if output.exists() or evidence.exists():
        parser.error('不覆盖既有TXT或分析记录')
    if not output.is_relative_to(ROOT) or not evidence.is_relative_to(ROOT):
        parser.error('输出须在本仓库内')

    frozen = read(ROOT/'experiments/a132_runtime_port_20261030/VALIDATION_SUMMARY.json')
    assert sha(BASE/'combined200/analysis.json') == frozen['baseline_analysis_sha256']
    baseline = read(BASE/'combined200/case_results.json')
    assert len(baseline) == len({r['case_id'] for r in baseline}) == 200
    # 合成汇总记录必须仍逐条来自原始150/17/33，而非后续小集拼分。
    origins = {}
    source_hashes = {}
    for name in ['train150', 'validation50', 'validation50_resume33', *ITERATIONS]:
        folder = BASE/name
        budget = read(folder/'budget.json')
        assert budget['status'] == 'closed'
        assert budget['plan_sha256'] == sha(folder/'plan.json')
        assert budget['trace_sha256'] == sha(folder/'live.jsonl')
        trace = [json.loads(line) for line in (folder/'live.jsonl').read_text().splitlines()]
        records = [r for r in trace if r.get('type') == 'case']
        assert read(folder/'case_results.json') == records
        assert sum(r.get('type') == 'request' for r in trace) == budget['used']
        source_hashes[str((folder/'live.jsonl').relative_to(ROOT))] = sha(folder/'live.jsonl')
        if name not in ITERATIONS:
            for row in records:
                assert row['case_id'] not in origins
                origins[row['case_id']] = row
    for row in baseline:
        original = origins[row['case_id']]
        assert {k:v for k,v in row.items() if k not in {'case_index', 'partition_case_index'}} == {
            k:v for k,v in original.items() if k != 'case_index'}

    split = ROOT/'datasets/whitebox_150_50_v1'
    manifest = read(split/'manifest.json')
    assert sha(split/'train.json') == manifest['train_sha256']
    assert sha(split/'sealed_test.json') == manifest['sealed_test_sha256']
    cases = {r['case_id']:r for name in ['train.json', 'sealed_test.json']
             for r in read(split/name)['cases']}
    assert set(cases) == set(origins)
    assert all(row['question'] == cases[row['case_id']]['question'] for row in baseline)
    curation = read(CLASSIFICATION)
    issues = curation['issues']
    gaps = {r['case_id']:r for r in baseline if r['score_without_time_penalty'] != 5}
    assert len(issues) == len({r['id'] for r in issues}) == len(gaps) == 56
    assert {r['id'] for r in issues} == set(gaps)
    assert all(r['group'] in ORDER for r in issues)
    for item in issues:
        if item.get('contract'):
            assert (ROOT/item['contract']).is_file()

    history = {}
    for name in ITERATIONS:
        for row in read(BASE/name/'case_results.json'):
            assert row['question'] == cases[row['case_id']]['question']
            history.setdefault(row['case_id'], []).append((name, row))
    assert all(history[i['id']][-1][1]['score_without_time_penalty'] == 5
               for i in issues if i['group'] == 'B_FIXED')
    api_scored = {r['case_id'] for r in baseline if 'API条件不合规' in r['reason']}
    api_internal = {r['case_id'] for r in baseline if
                    (r.get('diagnostics') or {}).get('missing_api_filter')}
    assert len(api_scored) == 33 and len(api_internal) == 4
    assert len(api_scored | api_internal) == 36
    counts = Counter(i['group'] for i in issues)
    partitions = Counter('训练150' if gaps[i['id']].get('training_case_index') else '验证50' for i in issues)
    group_partitions = {g: Counter('训练150' if gaps[i['id']].get('training_case_index') else '验证50'
                                  for i in issues if i['group'] == g) for g in ORDER}
    semantic = curation.get('additional_semantic_issues', [])
    by_id = {r['case_id']:r for r in baseline}
    assert all(i['id'] not in gaps and by_id[i['id']]['score_without_time_penalty'] == 5 for i in semantic)
    assert all((ROOT/i['evidence']).is_file() for i in semantic)
    timed_only = [r for r in baseline if r['score_without_time_penalty'] == 5 and r['score'] < 5]
    source_hashes.update({str(p.relative_to(ROOT)): sha(p) for p in [CLASSIFICATION, Path(__file__),
                           BASE/'combined200/analysis.json', BASE/'combined200/case_results.json']})
    for name in {i['contract'] for i in issues if i.get('contract')} | {i['evidence'] for i in semantic}:
        source_hashes[name] = sha(ROOT/name)

    title = '132版本：全部错误、API不合规与A/B/C分工清单（2026-10-31）'
    lines = [title, '='*66,
        '一、统计口径与结论',
        '依据：132 strict（26族+106固定），源码包db5ccb9，本地主干同步ec1e338。',
        '本次只读已有日志/合同/题目，不调用模型或数据服务、不执行SQL、不重评分，不改运行时代码、评分器或测试数据。',
        '200题基线为150+17+33分段同查询源码覆盖；质量分727.4/1000，144满分、6部分、17错误、33零分。',
        '这是修复前的基线，不是最新版重新跑200的分数；50题已曝光，只称验证集。',
        f'质量问题共56道：训练{partitions["训练150"]}道、验证{partitions["验证50"]}道。9道在后续小集取得满分，47道问题尚未关闭/未新验收；这不是最新版又实测47道错误。',
        '另附1道回归中新出现并修好的052，以及1道得5分但已知关联语义有误的057；两者不重复计入基线56道。基线仅时间扣分的11道另列。',
        '所有原题逐字来自原划分文件，仅用于归因与验收，禁止作为生产题号/整题/答案路由。', '']
    for group in ORDER:
        members = [i['id'] for i in issues if i['group'] == group]
        lines.append(f'{curation["groups"][group]}：{len(members)}道（'+', '.join(members)+'）')
    lines += ['', '按固定划分分开（训练/验证）：']
    for group in ORDER:
        lines.append(f'{curation["groups"][group]}：训练{group_partitions[group]["训练150"]} / 验证{group_partitions[group]["验证50"]}')
    lines.append('训练150尚未关闭24道＝5道已有合同待B接入＋5道待A补证据＋14道口径争议；不能把它们都当成新增模板需求。')
    lines += ['', '关键区别：',
        '- A_TEMPLATE的9道才是当前明确要求修改/扩展模板的清单；A_EVIDENCE的7道要先拿关系/schema/范围证据，不能承诺补字段即通过。',
        '- B_INTEGRATE的8道已有A合同，B接入且过原生门禁后才算支持；不是A没交付，也不是已经能得分。',
        '- C_REVIEW的15道不等于全部都是参考错误：包含范围/计数/类型/多资源输出争议及尚待验证的成因。',
        '- 128同时有AZ参考冲突；260同时有bool参考冲突；270同时有参考漏区域。按主要推进负责人归组，其他问题在逐题记录中保留。',
        '- 未全测新版；小集来自不同修订，不把逐题最新分加成新150/200成绩。', '',
        '二、API不合规总表（区分评分现象与真实根因）',
        '评分器明确报API条件不合规：33道；B内部missing_api_filter：4道；重叠224一题，去重共36道。',
        '33道评分API不合规均走过猜空，最终api_call为空；根因可能是填参、完整义务不足、schema或范围无法证明。不是33个模板都缺API条件。',
        'B内部四题：116缺region、224缺GaussDB AZ、275/288缺ELB AZ。116/275/288最终是-1，不是评分器API门槛0分，也必须跟进。',
        '其他语义问题（状态大小写、bool类型、错误租户/状态等）即使未触发门槛，也单列在对应原题，不当作API已语义正确。', '']
    for row in baseline:
        cid=row['case_id']
        if cid not in api_scored | api_internal:
            continue
        kinds=[]
        if cid in api_scored:kinds.append('评分API门槛0分')
        if cid in api_internal:kinds.append('B内部缺API筛选'+compact(row['diagnostics']['missing_api_filter'],180))
        later=history.get(cid, [])
        status=('；最新记录'+str(later[-1][1]['score_without_time_penalty'])+'分，'+later[-1][0]) if later else '；无后续真实复测记录'
        lines.append(cid+'：'+'；'.join(kinds)+status)

    structured=[]
    for n, group in enumerate(ORDER, 3):
        lines += ['', '='*66, f'{n}、{curation["groups"][group]}（{counts[group]}道）', '']
        for item in issues:
            if item['group'] != group:continue
            row=gaps[item['id']];reference=cases[item['id']];d=row.get('diagnostics') or {}
            part='训练150' if row.get('training_case_index') else '验证50（已曝光）'
            lines += [f'[{item["id"]} | {part}]', '原题：'+row['question'],
                f'基线：{row["score_without_time_penalty"]}分 / {grade(row)}；选中：{d.get("selected_template") or "无完整选中（见义务诊断）"}',
                '评分记录：'+row['reason'],
                '根因判断：'+item['why'], '下一步/交付：'+item['action'],
                '判断依据置信度：'+item['confidence']]
            if group == 'A_TEMPLATE':lines.append('A优先级：'+item['priority'])
            if item.get('contract'):lines.append('A已交付合同：'+item['contract'])
            reject=d.get('rejection') or {}
            if reject:lines.append('流程证据：'+compact(reject))
            if d.get('family_error'):lines.append('参数证据：'+d['family_error'])
            if d.get('resource_coverage',{}).get('unsupported'):
                lines.append('完整资源门禁缺项：'+compact(d['resource_coverage']['unsupported']))
            if d.get('missing_api_filter'):lines.append('缺失筛选证据：'+compact(d['missing_api_filter']))
            if group in {'A_TEMPLATE','A_EVIDENCE','B_INTEGRATE'} and d.get('template_sql'):
                lines.append('当前模板SQL：'+d['template_sql'])
            lines.append('实际最终API摘要：'+compact(api_summary(row.get('api_call'))))
            if group == 'C_REVIEW' or item['id'] in {'CMDB-106','CMDB-128','CMDB-260','CMDB-270'}:
                lines.append('参考API摘要：'+compact(api_summary(reference.get('api_call'))))
                result=row.get('result') or {}
                lines.append('参考/实际结果行数：'+str(reference.get('answer',{}).get('row_count'))+' / '+
                             str(result.get('row_count') if isinstance(result,dict) else '多结果集'))
            latest=[]
            for run, record in history.get(item['id'],[]):
                guess=bool((record.get('diagnostics') or {}).get('empty_answer_fallback'))
                latest.append({'run':run,'score':record['score_without_time_penalty'],'guess':guess})
                lines.append(f'后续真实记录：{run} → {record["score_without_time_penalty"]}分，猜空={guess}')
            if not latest:lines.append('后续状态：尚无新版真实复测，不能当作已修复或仍稳定复现。')
            lines.append('')
            structured.append(dict(item, question=row['question'], partition=part,
                                   baseline_score=row['score_without_time_penalty'], later_observations=latest))

    lines += ['九、补充记录：回归误拒与得分通过但语义有误（不重复计入基线56道）',
        '[CMDB-052：回归误拒已修]',
        '原题：'+cases['CMDB-052']['question'],
        '基线5分；v2回归显式投影格式被自然问法prepare拒绝，0分；v3仅复测052恢复5分。',
        'B负责相同API+SQL的受控格式转换；不是模板缺失。未用修复后052覆盖旧回归失败日志。','']
    for issue in semantic:
        row=by_id[issue['id']]
        lines += ['['+issue['id']+'：得分通过，语义问题仍未关闭]', '原题：'+row['question'],
                  '基线质量分：5；当前已记录SQL：'+row['sql'], '根因：'+issue['why'],
                  '分工：'+issue['action'], '证据：'+issue['evidence'], '置信度：'+issue['confidence'], '']
    lines.append('十、仅时间扣分（不列为A模板正确性需求）')
    for row in timed_only:
        lines.append(f'{row["case_id"]} | 质量5 / 计时{row["score"]} | 原题：{row["question"]}')
    lines += ['', '十一、独立请求失败与统计限制',
        'parameter_recovery_fail10在061的select发生1次APIConnectionError，SDK重试0；停止时只完成6题。',
        '061另获1次人工重试，与133/174/175作为tail4完成；费用日志中的失败请求保留，不当作模型拒答或模板不支持。',
        '验证50旧17题因本地目录迁移FileNotFoundError停止，剩33题是未请求后缀续跑，无重复题；三进程覆盖不称连续200。',
        '本次没有新增模型/服务请求，没有修改官方评分器/执行器，没有提交或推送运行时代码。', '',
        '十二、给A的交付约定与验收要求',
        '请优先处理A_TEMPLATE：128布尔类型合同；161/192完整网络关系；251按AZ三计数；260管理VM完整字段；298租户VM/EIP/HOST；299 CCE双计数。262/264随后处理。',
        'A_EVIDENCE先给权威字段、身份空间、关系与量词；缺依据继续标不支持。physical保持关闭，不给空CI伪造schema。',
        '每项给：现有族/新增view及参数schema、完整原文prepare、API+SQL、范围传播、ID/关联键、粒度、NULL/真空/失败/分页/未知/并列政策、合成正反例、固定路径/提交/哈希和模板数变化。',
        '仅在A职责文件提供隔离候选；保留B的query→_query猜空包装和原失败诊断，不覆盖matcher/system；官方四文件和原数据不改。',
        '若已有支持路径，给出族名/view/结构参数/完整物化输出及证据即可，不为每个题各建一个模板，不按原题/实体/题号硬编码。',
        '8道已交付合同主要交B，不需要重复交付；合同离线通过不等于原生接入或真实得分。',
        'A不负责替换争议参考答案；不要求A为15道C_REVIEW伪造错条件/错数。', '',
        '十三、来源', '基线记录：reports/a132_runtime_port_20261030/{train150,validation50,validation50_resume33,combined200}',
        '小集记录：reports/a132_runtime_port_20261030/{'+','.join(ITERATIONS)+'}',
        '分类依据：experiments/a132_error_triage_20261031/CLASSIFICATION.json',
        '生成器：scripts/build_a132_issue_handoff.py',
        '冻结证据指纹及A消息正文：'+str(evidence.relative_to(ROOT)),
        'A协作入口：https://github.com/getm0ss1moving/hackathon-p13-2/issues/3', '']

    a_lines=['A同学：132基线全部问题已归因，以下按本轮用户要求交接。',
        '基于db5ccb9的132 strict、主干ec1e338。此消息不提交运行时代码、不启用新合同、不要求改官方评测。',
        '56道基线质量问题里，明确A模板修改9道、A待证关系/schema7道；另8道已有A交付由B接入，不重复派工。9道填参误拒B已小集实测满分。50已曝光称验证集；只读既有记录，本轮无模型调用。',
        '下面原题用于归因/验收，禁止题号/整题/实体硬编码。', '']
    for group in ['A_TEMPLATE','A_EVIDENCE','B_INTEGRATE']:
        a_lines.append('### '+curation['groups'][group]+f'（{counts[group]}）')
        for item in issues:
            if item['group'] != group:continue
            row=gaps[item['id']];part='训练' if row.get('training_case_index') else '已曝光验证'
            a_lines += [f'**{item["id"]}（{part}，基线{row["score_without_time_penalty"]}分）**',
                        '原题：'+row['question'], '证据：'+item['why'], '要求：'+item['action']]
            if item.get('contract'):a_lines.append('已交付：`'+item['contract']+'`')
            a_lines.append('')
    a_lines += ['### 其他核查与边界',
        '057原题：'+cases['CMDB-057']['question'],
        '补充语义问题（不在基线56失分题中）：当前得5分但仍用fixedIpAddress=privateIps直接等号连接并返回空。请与298共用地址关联合同修复，明确多值编码与边界；B负责依赖contain语义/跨步/分批。证据：docs/handoffs/B_REVIEW_PEER_EMPTY14_20261030.md。',
        '077原题：'+cases['CMDB-077']['question'],
        '已有rb_052，不请求新模板；原题未给区域而参考给默认区域，C先定范围。请A核对R4是否把“CPU架构类型并统计各类数量”错误拆成独立义务。',
        '123原题：'+cases['CMDB-123']['question'],
        '实际/参考COUNT0与1先交C核验；参考也未输出类型。若确认需类型分组，再明确VOLUME类型关系并扩展view，目前不冒充单一模板错误。',
        '其余参考争议：024/028/051/053/088/102/112/115/166/252/256/259/274交C或B核验。053题文与参考租户不同，不能交换实体凑分。',
        '交付：通用family/view+必需参数schema、完整原文prepare、可执行API+SQL、关联/范围/粒度/NULL/分页/空与失败政策、未知/并列控制、实体替换和额外义务反例、固定提交/路径/哈希、实际模板数变化。优先复用原族。',
        '请先给隔离候选，保留已交付包原字节。B负责接入与小集验收；不覆盖B matcher/system，不改官方executor/evaluator/quick/black或原始数据，不自动调用新模型。',
        '完整本地TXT：docs/handoffs/'+output.name+'（本次未推送源码，A需跨机器材料时以本消息完整摘录为准）。']

    output.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=False)
    with output.open('x') as file:file.write('\n'.join(lines))
    with (evidence/'A_MESSAGE.json').open('x') as file:
        json.dump({'body':'\n\n'.join(a_lines)},file,ensure_ascii=False,indent=2);file.write('\n')
    with (evidence/'records.json').open('x') as file:
        json.dump(structured,file,ensure_ascii=False,indent=2);file.write('\n')
    check={'status':'complete','baseline_issues':len(gaps),'partition_counts':dict(partitions),
           'group_counts':dict(counts),'group_partition_counts':{k:dict(v) for k,v in group_partitions.items()},
           'additional_semantic_issue_ids':[i['id'] for i in semantic],
           'scorer_api_gate':len(api_scored),'internal_missing_api_filter':len(api_internal),
           'api_issue_union':len(api_scored | api_internal),'resolved_in_later_subsets':counts['B_FIXED'],
           'unclosed_historical_issues':len(gaps)-counts['B_FIXED'],'timed_only_not_quality_errors':len(timed_only),
           'original_questions_verified':True,'scoring_recomputed':False,'model_requests':0,'service_requests':0,
           'production_source_modified':False,'output':str(output.relative_to(ROOT)),'output_sha256':sha(output),
           'sources_sha256':source_hashes,'generator_command':[str(Path(__file__).relative_to(ROOT)),
              '--output',str(args.output),'--evidence-dir',str(args.evidence_dir)]}
    with (evidence/'VERIFY.json').open('x') as file:
        json.dump(check,file,ensure_ascii=False,indent=2);file.write('\n')
    print(json.dumps({k:v for k,v in check.items() if k != 'sources_sha256'},ensure_ascii=False))


if __name__ == '__main__':main()
