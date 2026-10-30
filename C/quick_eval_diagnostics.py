"""C扩展诊断入口；非主办方原脚本，评分仍调用原evaluate_case。"""

import argparse
import http.client
import json
import logging
import os
import sys
import time

_HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "implementation")
sys.path.insert(0, _HERE)


def main(argv=None):
    parser = argparse.ArgumentParser(description="白盒单次本地诊断，不代表正式成绩")
    parser.add_argument("N", nargs="?", type=int, default=20, help="运行前 N 题，默认 20")
    parser.add_argument("--report", help="可选 JSONL 详细结果路径；不覆盖旧文件")
    args = parser.parse_args(argv)
    if args.N < 1:
        parser.error("N 必须为正整数")

    test_file = os.path.join(os.path.dirname(_HERE), "CMDB用例集-白盒200.json")
    if not os.path.isfile(test_file):
        parser.error(f"白盒用例文件缺失: {test_file}")
    try:
        with open(test_file, encoding="utf-8") as f:
            all_cases = json.load(f)["cases"]
    except (OSError, ValueError, KeyError) as exc:
        parser.error(f"无法加载白盒用例: {exc}")
    if args.N > len(all_cases):
        parser.error(f"N={args.N} 超过实际用例数 {len(all_cases)}")
    cases = all_cases[:args.N]

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        parser.error("请先在本机配置 DEEPSEEK_API_KEY；不要在聊天、代码或日志中发送密钥")

    connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=2)
    try:
        connection.request("GET", "/rest/hackthon/db/schema/VM_NOVA")
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("schema HTTP 状态异常")
        schema = json.loads(response.read())
        if (not isinstance(schema, dict) or schema.get("ci_name") != "VM_NOVA"
                or not isinstance(schema.get("columns"), list) or not schema["columns"]
                or not all(isinstance(column, str) for column in schema["columns"])
                or type(schema.get("row_count")) is not int or schema["row_count"] < 0):
            raise ValueError("schema 结构异常")
    except (OSError, http.client.HTTPException, ValueError, TypeError) as exc:
        print(f"本地数据服务未就绪（{type(exc).__name__}），评估未开始；请先启动 127.0.0.1:8080 的原数据服务", file=sys.stderr)
        return 1
    finally:
        connection.close()

    try:
        from runbook_system import RunbookQuerySystem
        from evaluator import evaluate_case
    except ImportError as exc:
        parser.error(f"查询依赖导入失败: {exc}；请使用已安装依赖的虚拟环境")

    from eval_report import EvaluationReport

    try:
        with EvaluationReport(args.report, test_file, len(cases)) as report:
            logging.disable(logging.CRITICAL)
            try:
                system = RunbookQuerySystem()
            except Exception as exc:
                report.stop_reason = f'系统初始化失败（{type(exc).__name__}）'
                print(f"系统初始化失败（{type(exc).__name__}），评估未开始", file=sys.stderr)
                return 1

            print(f"本地诊断：白盒前 {len(cases)} 题，每题 1 次；不含正式重复平均、黑白加权或模板数量分。")
            total_score = 0
            correct = wrong = no_answer = partial = 0
            for index, case in enumerate(cases):
                diagnostics = {} if args.report else None
                t0 = time.perf_counter()
                try:
                    if diagnostics is None:
                        output = system.query(case["question"])
                    else:
                        output = system.query(case["question"], diagnostics=diagnostics)
                except Exception as exc:
                    report.stop_reason = f"{case['case_id']}: 查询异常（{type(exc).__name__}）"
                    report.query_error(case, exc, diagnostics)
                    print(f"{case['case_id']}: 查询异常（{type(exc).__name__}）；评估中止，已完成 {index}/{len(cases)} 题，未生成完整基线", file=sys.stderr)
                    return 1
                elapsed = time.perf_counter() - t0
                result = evaluate_case(case, output, elapsed)
                report.record(case, output, result, elapsed, diagnostics)
                total_score += result["score"]
                if result["score"] == 5:
                    correct += 1
                elif result["score"] < 0:
                    wrong += 1
                elif result["score"] == 0:
                    no_answer += 1
                else:
                    partial += 1
                print(f"{case['case_id']}: {result['score']:+} ({result['reason'][:70]}) [{elapsed:.1f}s]")

            count = len(cases)
            pct = total_score / (count * 5) * 100
            print(f"\n=== {count} cases: score={total_score}/{count*5}, correct={correct}, partial={partial}, wrong={wrong}, no_answer={no_answer}, pct={pct:.1f}% ===")
            report.complete()
            if args.report:
                print(f"详细结果：{os.path.abspath(args.report)}")
            return 0
    except OSError as exc:
        print(f"结果文件读写失败（{type(exc).__name__}），评估停止；请使用新的可写 --report 路径", file=sys.stderr)
        return 1



if __name__ == "__main__":
    sys.exit(main())
