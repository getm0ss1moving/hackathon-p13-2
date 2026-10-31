"""加载本机132配置运行官方入口，或显式复用C的逐题诊断；--check不调用模型。"""

import argparse
import ast
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import urllib.request
from zoneinfo import ZoneInfo

from check_official_integrity import require_official_files


ROOT = Path(__file__).resolve().parents[1]

# 同一组环境参数转换到已冻结的 B 诊断入口；每个子进程独立计数。
TRAINING_FLAGS = {
    'RUNBOOK_REFINE_CONTRACT_PROMPT':'--refine-contract-prompt',
    'RUNBOOK_COMPLETE_INDEPENDENT_AGGREGATES':'--independent-aggregates',
    'RUNBOOK_COMPLETE_GROUPED_AGGREGATES':'--grouped-aggregates',
    'RUNBOOK_COMPLETE_NETWORK_DETAILS':'--network-details',
    'RUNBOOK_COMPLETE_IDENTITY_PROJECTION':'--identity-projection',
    'RUNBOOK_COMPLETE_VPC_SUBNETS':'--vpc-subnets',
    'RUNBOOK_COMPLETE_TENANT_RESOURCES':'--tenant-resources',
    'RUNBOOK_COMPLETE_VM_VOLUME_DETAILS':'--vm-volume-details',
    'RUNBOOK_BIND_TENANT_VDC':'--tenant-vdc-binding',
    'RUNBOOK_COMPLETE_PARALLEL_LISTS':'--parallel-resource-lists',
    'RUNBOOK_SG_RULE_SEMIJOIN':'--sg-rule-semijoin',
    'RUNBOOK_VERIFIED_EMPTY_ROOT':'--verified-empty-root',
    'RUNBOOK_TYPED_EMPTY_ROOT':'--typed-empty-root',
    'RUNBOOK_COMPLETE_DETAIL_COUNT':'--detail-count',
    'RUNBOOK_COMPLETE_CCE_DETAILS':'--cce-cluster-details',
    'RUNBOOK_CLUSTER_RANK_DETAILS':'--cluster-rank-details',
    'RUNBOOK_VDC_RESOURCE_COUNTS':'--vdc-resource-counts',
    'RUNBOOK_GROUND_SQL_MEASURES':'--ground-sql-measures',
    'RUNBOOK_PARTIAL_STORAGE_POOLS':'--partial-storage-pools',
    'RUNBOOK_PRESERVE_SPARSE_NULLS':'--preserve-sparse-nulls',
    'RUNBOOK_BIND_DEPLOY_NODE_REGION':'--bind-deploy-node-region',
    'RUNBOOK_ISSUE3_CONTRACTS':'--issue3-contracts',
    'RUNBOOK_A132_NATIVE_BOOTABLE':'--native-bootable',
    'RUNBOOK_ISSUE4_NETWORK':'--issue4-network',
    'RUNBOOK_ISSUE4_VM_LINKS':'--issue4-vm-links',
    'RUNBOOK_ISSUE4_AZ_COUNTS':'--issue4-az-counts',
}


def training_arguments(environment, first, last):
    grouped = [environment[name] for name in ('RUNBOOK_PRESERVE_AGGREGATE_GRAIN',
        'RUNBOOK_PRESERVE_LITERAL_LABELS','RUNBOOK_PRUNE_UNUSED_LOOKUPS','RUNBOOK_GROUND_ENUM_LABELS')]
    if len(set(grouped))!=1 or grouped[0] not in {'0','1'}:
        raise ValueError('候选保护参数必须一起启停')
    result=['--a132-candidate','--thinking-mode',environment['RUNBOOK_THINKING_MODE']]
    if grouped[0]=='1':result.append('--candidate-flags')
    for name,flag in TRAINING_FLAGS.items():
        value=environment.get(name,'0')
        if value not in {'0','1'}:raise ValueError('无效的布尔参数：'+name)
        if value=='1':result.append(flag)
    if environment['RUNBOOK_EMPTY_ANSWER_FALLBACK']=='0':result.append('--no-empty-answer-fallback')
    for profile in json.loads(environment['RUNBOOK_ISSUE3_PROFILES']):
        result+=['--issue3-profile',profile]
    families=json.loads(environment.get('RUNBOOK_ISSUE4_NETWORK_FAMILIES','null'))
    if families is not None:
        for family in families:result+=['--issue4-network-family',family]
    return result+['--whitebox200','--whitebox-first',str(first),'--whitebox-last',str(last),
                   '--request-limit',str(3*(last-first+1))]


def bounded_ranges(cases, batch_size):
    if type(cases) is not int or not 1<=cases<=200 or type(batch_size) is not int or not 1<=batch_size<=150:
        raise ValueError('题数须1至200；每批须1至150')
    return [(first,min(first+batch_size-1,cases)) for first in range(1,cases+1,batch_size)]


def run_bounded_batches(environment, cases, batch_size, output, plan_only=False):
    """复用原 B 冻结/账本与原 evaluate_case；任何不完整批次都停止，禁止补零拼分。"""
    from analyze_whitebox_batches import read_batch,combine_batches
    output=output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    wrappers=['scripts/run_a132_eval.py','scripts/run_saved_training.py','scripts/analyze_whitebox_batches.py']
    wrapper_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in wrappers}
    jobs=[];reference=None
    for index,(first,last) in enumerate(bounded_ranges(cases,batch_size),1):
        directory=output/f'part{index:02d}'
        config={'arguments':training_arguments(environment,first,last),'output_dir':str(directory)}
        path=output/f'part{index:02d}.config.json'
        path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
        command=[sys.executable,'-B',str(ROOT/'scripts/run_saved_training.py'),'--config',str(path)]
        process=subprocess.run(command,cwd=ROOT,env=environment,text=True,capture_output=True)
        (output/f'part{index:02d}.preflight.log').write_text(process.stdout+process.stderr)
        if process.returncode:raise ValueError('分批预检失败，未调用模型；见 '+str(output))
        plan=json.loads((directory/'plan.json').read_text())
        common={key:plan[key] for key in ('source_sha256','feature_flags','model','base_url','thinking_mode',
            'max_output_tokens','sdk_max_retries','scoring_revision','evaluation_sha256','code_base')}
        if reference is not None and reference!=common:raise ValueError('分批候选/配置漂移，未调用模型')
        if plan['max_requests']!=3*(last-first+1) or plan['max_requests']>450:
            raise ValueError('分批请求上限异常，未调用模型')
        reference=common
        jobs.append({'range':[first,last],'maximum':plan['max_requests'],'directory':str(directory),
                     'command':command+['--run']})
    manifest={'status':'frozen','cases':cases,'batch_size':batch_size,'single_process_round':False,
        'maximum_total_requests':sum(job['maximum'] for job in jobs),'model_requests_at_freeze':0,
        'wrapper_sha256':wrapper_hashes,'common_plan':reference,'jobs':jobs}
    (output/'batch_plan.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'分批计划：{output / "batch_plan.json"}；共{len(jobs)}批；合计最多{manifest["maximum_total_requests"]}次请求',flush=True)
    if plan_only:
        print('仅冻结计划，未调用模型。',flush=True)
        return 0
    for job in jobs:
        if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in wrapper_hashes.items()):
            raise ValueError('分批启动器漂移，停止后续请求')
        print('运行命令：'+shlex.join(job['command']),flush=True)
        with (Path(job['directory'])/'launcher.log').open('x') as log:
            code=subprocess.run(job['command'],cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT).returncode
        if code:raise ValueError('分批中断，保留已有结果；不生成完整总分：'+job['directory'])
        # 先校验当前批的身份、覆盖、账本和原始记录，再发起下一批。
        batch=read_batch(job['directory'])
        print(json.dumps({'range':job['range'],'completed':batch['summary']['completed_cases'],
                          'quality':batch['summary']['untimed_score'],'requests':batch['budget']['used']},ensure_ascii=False),flush=True)
    report,rows=combine_batches([job['directory'] for job in jobs],expected_count=cases)
    combined=output/'combined';combined.mkdir(exist_ok=False)
    for name,value in [('analysis.json',report),('case_results.json',rows),('failures.json',report['failure_details'])]:
        (combined/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'complete','cases':cases,'overall':report['overall'],
                      'generation_requests':report['generation_requests'],'output_dir':str(combined)},ensure_ascii=False),flush=True)
    return 0


def read_environment(path, allowed):
    values = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, raw = line.partition("=")
        name = name.strip().removeprefix("export ")
        if not separator or not allowed(name):
            continue
        parts = shlex.split(raw, comments=True)
        if len(parts) > 1:
            raise ValueError(f"配置项 {name} 需要用引号包裹含空格的值")
        values[name] = parts[0] if parts else ""
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="?", type=int, default=200, help="原白盒前N题，默认200")
    parser.add_argument("--check", action="store_true", help="只检查132模板、依赖、密钥配置和本地服务")
    parser.add_argument("--diagnostics", action="store_true",
                        help="改用既有C诊断入口保存完整逐题JSONL；评分仍用原evaluate_case")
    parser.add_argument('--plan-only',action='store_true',help='只冻结连续分批计划、源码和配置；不调用模型')
    parser.add_argument('--batch-size',type=int,default=20,help='超过150题或--plan-only时每批题数，1至150，默认20')
    parser.add_argument('--output-dir',type=Path,help='连续分批结果的新目录；不覆盖旧结果')
    args = parser.parse_args()
    if not 1 <= args.cases <= 200:
        parser.error("题数必须在1至200之间")
    if not 1<=args.batch_size<=150:
        parser.error('每批题数须1至150')
    batched=args.cases>150 or args.plan_only or args.output_dir is not None

    try:
        for package in ("openai", "httpx", "requests"):
            if importlib.util.find_spec(package) is None:
                raise ValueError("缺少查询依赖，请使用项目的 .venv/bin/python")
        require_official_files(ROOT)
        tree = ast.parse((ROOT / "implementation/runbook_items.py").read_text(encoding="utf-8"))
        items = next(ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "RUNBOOK_ITEMS"
                             for target in node.targets))
        if len(items) != 132 or len({item["id"] for item in items}) != 132:
            raise ValueError("当前目录未加载132条唯一模板，评测未启动")
        sys.path.insert(0,str(ROOT/'implementation'))
        from runbook_matcher import _verify_a132_sources
        from runbook_bootable_native import sources as bootable_sources
        from runbook_cluster_rank_details import sources as cluster_rank_sources
        from runbook_issue4 import sources as issue4_sources
        _,_,runtime_variant=_verify_a132_sources(ROOT)
        bootable_sources()
        cluster_rank_sources()
        issue4_sources()
        from runbook_issue4_vm_links import module as consumer_module
        consumer_module().provider()
        from runbook_issue4_az import module as az_module
        az_module()
        environment = os.environ.copy()
        environment.update(read_environment(ROOT / ".env.local", lambda name: name in {
            "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "RUNBOOK_LLM_TIMEOUT"}))
        environment.update(read_environment(ROOT / "configs/train150_v18.env", lambda name:
                                            name.startswith(("RUNBOOK_", "DEEPSEEK_"))))
        environment.update({
            "RUNBOOK_A132_CANDIDATE": "1",
            "RUNBOOK_MAX_LLM_CALLS": str(min(args.cases * 3,450)),
            "RUNBOOK_COMPLETE_DETAIL_COUNT": "1",
            "RUNBOOK_GROUND_SQL_MEASURES": "1",
            "RUNBOOK_PARTIAL_STORAGE_POOLS": "1",
            "RUNBOOK_SG_RULE_SEMIJOIN": "1",
            "RUNBOOK_VERIFIED_EMPTY_ROOT": "1",
            "RUNBOOK_TYPED_EMPTY_ROOT": "1",
            "RUNBOOK_EMPTY_ANSWER_FALLBACK": "1",
            "RUNBOOK_PRESERVE_SPARSE_NULLS": "0",
            "RUNBOOK_BIND_DEPLOY_NODE_REGION": "1",
            "RUNBOOK_ISSUE3_CONTRACTS": "1",
            "RUNBOOK_ISSUE3_PROFILES": json.dumps(["namespace_counts","tenant_lists","vdc_network"]),
            "RUNBOOK_A132_NATIVE_BOOTABLE": "1",
            "RUNBOOK_COMPLETE_CCE_DETAILS": "1",
            "RUNBOOK_CLUSTER_RANK_DETAILS": "1",
            "RUNBOOK_VDC_RESOURCE_COUNTS": "0",
            "RUNBOOK_ISSUE4_NETWORK": "1",
            "RUNBOOK_ISSUE4_NETWORK_FAMILIES": json.dumps(['hierarchy']),
            "RUNBOOK_ISSUE4_VM_LINKS": "1",
            "RUNBOOK_ISSUE4_AZ_COUNTS": "1",
        })
        if not environment.get("DEEPSEEK_API_KEY", "").strip():
            raise ValueError("本机未配置DEEPSEEK_API_KEY，请在.env.local配置；不要发送密钥")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8080/rest/hackthon/db/schema/VM_NOVA", timeout=3) as response:
            schema = json.load(response)
        if schema.get("ci_name") != "VM_NOVA" or not schema.get("columns"):
            raise ValueError("8080端口不是预期的原版数据服务")
    except (ValueError, OSError, StopIteration, SyntaxError) as exc:
        # 不输出第三方异常正文，避免意外回显配置内容。
        safe_message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
        print(f"预检未通过：{safe_message}", file=sys.stderr)
        print("如服务未启动，请另开终端执行：.venv/bin/python output-server/data_server.py --host 127.0.0.1 --port 8080", file=sys.stderr)
        return 1

    description = (f"132模板；原白盒前{args.cases}题；{environment['DEEPSEEK_MODEL']}；"
                   f"thinking={environment['RUNBOOK_THINKING_MODE']}；"
                   f"合计最多{args.cases*3}次模型请求；猜空兜底开启")
    print(description, flush=True)
    print('检索配对：'+runtime_variant,flush=True)
    print("入口：" + ('B连续分批诊断（原query/evaluate_case；每批新进程和缓存，不是官方单进程成绩）' if batched else
                      "C诊断（原评分函数）" if args.diagnostics else "官方quick_eval（原文件）"), flush=True)
    print("A合同启用：" + ", ".join(json.loads(environment["RUNBOOK_ISSUE3_PROFILES"])), flush=True)
    print("原生bootable合同：开启（保留原文region/AZ；不转换管理VM布尔类型）", flush=True)
    print("集群排名明细：开启（已知领先者＋完整审计计数；未知人口保留，不认证全域最大）", flush=True)
    print('A新网络合同：hierarchy开启；named_vpc保持关闭；完整图明细保留，业务完整性未认证',flush=True)
    print('VM/EIP合同：开启；租户目录与已证端口关联分列，完整绑定未认证',flush=True)
    print('AZ人口合同：开启；原始VM标签与完整A分组保留，VPC部署AZ仍未知',flush=True)
    if args.check:
        print("预检通过，未调用模型。", flush=True)
        return 0

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S_%f")
    if batched:
        output=args.output_dir or reports/f'a132_batches_{timestamp}'
        try:
            return run_bounded_batches(environment,args.cases,args.batch_size,output,args.plan_only)
        except (ValueError,OSError) as exc:
            print(f'连续分批停止：{exc}',file=sys.stderr)
            return 1
    log_path = reports / f"a132_whitebox{args.cases}_{timestamp}.log"
    print(f"结果日志：{log_path}", flush=True)
    command = [sys.executable, "-u", "-B", str(ROOT / "implementation/quick_eval.py"), str(args.cases)]
    if args.diagnostics:
        detail_path = reports / f"a132_whitebox{args.cases}_{timestamp}.jsonl"
        command = [sys.executable, "-u", "-B", str(ROOT / "C/quick_eval_diagnostics.py"),
                   str(args.cases), "--report", str(detail_path)]
        print(f"逐题诊断：{detail_path}", flush=True)
    with log_path.open("x", encoding="utf-8") as log:
        log.write(description + "\n")
        log.flush()
        child = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        try:
            for line in child.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            return child.wait()
        except KeyboardInterrupt:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
            child.wait()
            print(f"\n评测已中断，已有日志保留：{log_path}", file=sys.stderr)
            return 130
        finally:
            child.stdout.close()


if __name__ == "__main__":
    raise SystemExit(main())
