"""B训练工具的同次查询完整输出归档；不参与查询或评分。"""
import gzip
import hashlib
import json
from pathlib import Path

from run_whitebox import result_preview

RAW_OUTPUT_POLICY = {"format": "query-output-json-gzip-v1", "complete_query_output": True,
                     "overwrite": False, "capture": "system.query return value before scoring"}


def save_raw_output(trace_path, case_index, case_id, output):
    if type(case_index) is not int or case_index < 1 or not isinstance(output, dict):
        raise ValueError("完整输出必须包含有效题序与查询对象")
    trace_path = Path(trace_path)
    payload = {"case_index": case_index, "case_id": case_id, "output": output}
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    relative = Path("live_outputs") / trace_path.stem / f"{case_index:06d}.json.gz"
    target = trace_path.parent / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(compressed)
    return {"format": RAW_OUTPUT_POLICY["format"], "path": relative.as_posix(),
            "sha256": hashlib.sha256(compressed).hexdigest(), "bytes": len(compressed)}


def verify_raw_output(directory, row):
    """校验新格式记录的完整输出和日志预览确属同次查询；不重新评分。"""
    reference = row.get("raw_output")
    if not isinstance(reference, dict) or reference.get("format") != RAW_OUTPUT_POLICY["format"]:
        raise ValueError("缺少完整输出引用或格式不符")
    directory = Path(directory).resolve()
    path = (directory / reference["path"]).resolve()
    if not path.is_relative_to(directory) or path == directory:
        raise ValueError("完整输出路径不在本轮目录内")
    compressed = path.read_bytes()
    if (hashlib.sha256(compressed).hexdigest() != reference.get("sha256")
            or len(compressed) != reference.get("bytes")):
        raise ValueError("完整输出指纹或长度不符")
    payload = json.loads(gzip.decompress(compressed))
    if (type(payload.get("case_index")) is not int or payload["case_index"] != row["case_index"]
            or payload.get("case_id") != row["case_id"] or not isinstance(payload.get("output"), dict)):
        raise ValueError("完整输出题目身份不符")
    output = payload["output"]
    mirrors = {key: output.get(key) for key in ("matched_runbook", "api_call", "sql", "diagnostics")}
    mirrors["result"] = result_preview(output.get("result"))
    # JSON比较同时区分原生布尔、数值和字符串。
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if any(encode(value) != encode(row.get(key)) for key, value in mirrors.items()):
        raise ValueError("完整输出与同轮日志预览不符")
    return output
