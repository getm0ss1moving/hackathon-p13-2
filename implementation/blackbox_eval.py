import sys, json, time, logging, os
logging.disable(logging.CRITICAL)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from runbook_system import RunbookQuerySystem
from evaluator import evaluate_case

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100

f = open(os.path.join(os.path.dirname(_HERE), 'CMDB用例集-黑盒100.json'), encoding='utf-8')
cases = json.load(f)['cases'][:N]

system = RunbookQuerySystem()

total_score = 0
correct = 0
wrong = 0
no_answer = 0
partial = 0

for c in cases:
    cid = c['case_id']
    q = c['question']
    t0 = time.time()
    try:
        output = system.query(q)
    except Exception as e:
        output = {'error': str(e), 'matched_runbook': None, 'result': None, 'api_call': None}
    elapsed = time.time() - t0
    
    result = evaluate_case(c, output, elapsed)
    total_score += result['score']
    if result['score'] == 5:
        correct += 1
    elif result['score'] < 0:
        wrong += 1
    elif result['score'] == 0:
        no_answer += 1
    else:
        partial += 1
    
    status = "+" + str(result['score']) if result['score'] > 0 else str(result['score'])
    print(cid + ": " + status + " (" + result['reason'][:70] + ") [" + str(round(elapsed, 1)) + "s]")

avg = total_score / (N * 5) * 100 if N > 0 else 0
print(f"\n=== {N} cases: score={total_score}/{N*5}, correct={correct}, partial={partial}, wrong={wrong}, no_answer={no_answer}, pct={avg:.1f}% ===")
