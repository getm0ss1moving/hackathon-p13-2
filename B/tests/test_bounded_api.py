"""有界 API 编排合同；本文件只使用内存响应，不访问模型或真实数据服务。"""

import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
import runbook_executor as executor
import runbook_matcher as matcher
import runbook_system as system


def call(ci, *constraints):
    return {"method": "GET", "url": f"/rest/hackthon/db/instances/{ci}",
            "condition": {"constraint": [{"simple": {"name": field, "operator": operator, "value": value}}
                                          for field, operator, value in constraints]}}


def book(*calls, sql):
    return {"id": "fixture", "name": "合同测试", "api_call": list(calls), "sql": sql}


JOIN_SQL = "SELECT COUNT(*) AS count FROM CLOUD_HOST h JOIN CLOUD_VM_NOVA v ON v.hostId=h.id"


class MemorySession:
    def __init__(self, database, responder=None):
        self.database = database
        self.requests = []
        self.responder = responder

    def get(self, url, **kwargs):
        parsed = urlsplit(url)
        ci, query = parsed.path.rsplit("/", 1)[1], parse_qs(parsed.query)
        constraints = json.loads(query.get("condition", ['{"constraint":[]}'])[0])["constraint"]
        self.requests.append({"ci": ci, "constraints": constraints, "url": url, **kwargs})
        if self.responder:
            special = self.responder(self, ci, query)
            if special is not None:
                return special
        rows = copy.deepcopy(self.database[ci])
        for constraint in constraints:
            simple = constraint["simple"]
            field, value, operator = simple["name"], simple["value"], simple["operator"]
            if operator == "in":
                rows = [row for row in rows if row.get(field) in value]
            elif operator == "equal":
                rows = [row for row in rows if row.get(field) == value]
            elif operator == "contain":
                rows = [row for row in rows if value in str(row.get(field, ""))]
        page, size = int(query["pageNo"][0]), int(query["pageSize"][0])
        payload = {"objList": rows[(page-1)*size:page*size], "totalNum": len(rows), "pageSize": size,
                   "totalPageNo": (len(rows)+size-1)//size, "currentPage": page}
        return SimpleNamespace(status_code=200, json=lambda: payload)


class BoundedAPITests(unittest.TestCase):
    def setUp(self):
        schema = patch.object(matcher, "_schema_columns", {
            "HOST": ["id", "name"], "VM_NOVA": ["id", "name", "hostId"],
            "SECURITY_GROUP": ["id", "name"],
            "SECURITY_GROUP_RULE": ["id", "securityGroupId", "direction", "protocol", "weight"],
        })
        schema.start()
        self.addCleanup(schema.stop)
        no_model = patch.object(matcher, "llm_ask", side_effect=AssertionError("禁止模型调用"))
        no_model.start()
        self.addCleanup(no_model.stop)
        self.database = {"HOST": [{"id": "h1", "name": "first"}, {"id": "h2", "name": "second"}],
                         "VM_NOVA": [{"id": "v1", "name": "vm1", "hostId": "h1"},
                                     {"id": "v2", "name": "vm2", "hostId": "h2"}]}

    def execute(self, item, database=None, **limits):
        session = MemorySession(self.database if database is None else database)
        diagnostics = {}
        result = system._execute_bounded_api(item, diagnostics, session=session, **limits)
        return result, diagnostics, session

    def dependent(self, sql=JOIN_SQL):
        return book(call("HOST"), call("VM_NOVA", ("hostId", "in", "{{id from step 1}}")), sql=sql)

    def test_nonempty_dependency_uses_real_values_and_does_not_write_cache(self):
        item = self.dependent()
        original, cache = copy.deepcopy(item), copy.deepcopy(executor._cache)
        result, diagnostics, session = self.execute(item)
        self.assertEqual(result["result"]["rows"], [{"count": 2}])
        self.assertTrue(diagnostics["sql_executed"])
        self.assertEqual(len(session.requests), 2)
        self.assertEqual(session.requests[1]["constraints"][0]["simple"]["value"], ["h1", "h2"])
        self.assertEqual(item, original)
        self.assertEqual(executor._cache, cache)

    def test_empty_input_executes_empty_join_sql_without_target_request(self):
        self.database["HOST"] = []
        result, diagnostics, session = self.execute(self.dependent())
        self.assertEqual(result["result"]["rows"], [{"count": 0}])
        self.assertEqual([row["ci"] for row in session.requests], ["HOST"])
        self.assertEqual(diagnostics["short_circuit"], "empty_inner_join_input")
        self.assertTrue(diagnostics["sql_executed"])

    def test_empty_unproven_or_lookup_dependency_refuses_before_target(self):
        self.database["HOST"] = []
        for sql, sources, reason in [
            ("SELECT name FROM CLOUD_VM_NOVA", (), "empty_dependency_source"),
            (JOIN_SQL, ("CLOUD_HOST",), "empty_lookup_source"),
            (JOIN_SQL.replace("JOIN", "LEFT JOIN"), (), "empty_dependency_source"),
        ]:
            with self.subTest(reason=reason):
                session, diagnostics = MemorySession(self.database), {}
                with self.assertRaisesRegex(system._APIPlanRefusal, reason):
                    system._execute_bounded_api(self.dependent(sql), diagnostics, session=session, lookup_sources=sources)
                self.assertEqual(len(session.requests), 1)
                self.assertFalse(diagnostics["sql_executed"])

    def test_missing_null_or_structural_dependency_never_broadens(self):
        for rows, reason in [([{"name": "missing"}], "missing_dependency_values"),
                             ([{"id": None}], "missing_dependency_values"),
                             ([{"id": "h1"}, {"name": "missing"}], "missing_dependency_values"),
                             ([{"id": []}], "unusable_dependency_value"),
                             ([{"id": False}], "unusable_dependency_value")]:
            with self.subTest(rows=rows):
                session, diagnostics = MemorySession({**self.database, "HOST": rows}), {}
                with self.assertRaisesRegex(system._APIPlanRefusal, reason):
                    system._execute_bounded_api(self.dependent(), diagnostics, session=session)
                self.assertEqual(len(session.requests), 1)

    def test_zero_dependency_is_preserved(self):
        database = {"HOST": [{"id": 0}], "VM_NOVA": [{"id": "v0", "hostId": 0}]}
        result, _, session = self.execute(self.dependent(), database)
        self.assertEqual(result["result"]["rows"], [{"count": 1}])
        self.assertEqual(session.requests[1]["constraints"][0]["simple"]["value"], [0])

    def test_invalid_reference_or_unverified_field_stops_before_any_http(self):
        for reference, reason in [("{{id from step 2}}", "nonadjacent_or_invalid_dependency"),
                                  ("{{unknown from step 1}}", "unverified_dependency_field"),
                                  ("{{ID FROM STEP 1}}", "nonadjacent_or_invalid_dependency")]:
            with self.subTest(reference=reference):
                item = book(call("HOST"), call("VM_NOVA", ("hostId", "in", reference)), sql=JOIN_SQL)
                session = MemorySession(self.database)
                with self.assertRaisesRegex(system._APIPlanRefusal, reason):
                    system._execute_bounded_api(item, {}, session=session)
                self.assertEqual(session.requests, [])
        item = self.dependent()
        item["api_call"][1]["url"] += "?x={{id from step 1}}"
        with self.assertRaisesRegex(system._APIPlanRefusal, "unsupported_dependency_location"):
            system._execute_bounded_api(item, {}, session=MemorySession(self.database))

    def rule_book(self):
        return book(call("SECURITY_GROUP_RULE", ("securityGroupId", "in", ["g1", "g2", "g1", "g3"]),
                         ("direction", "equal", "ingress")),
                    sql="SELECT direction, COUNT(*) AS n, COUNT(DISTINCT protocol) AS kinds, AVG(weight) AS avg_weight "
                        "FROM CLOUD_SECURITY_GROUP_RULE GROUP BY direction")

    def rules(self):
        return {"SECURITY_GROUP_RULE": [
            {"id": "r1", "securityGroupId": "g1", "direction": "ingress", "protocol": "tcp", "weight": 2},
            {"id": "r2", "securityGroupId": "g2", "direction": "ingress", "protocol": "tcp", "weight": 4},
            {"id": "r3", "securityGroupId": "g3", "direction": "ingress", "protocol": "udp", "weight": 12},
            {"id": "r4", "securityGroupId": "g3", "direction": "egress", "protocol": "udp", "weight": 99}]}

    def test_all_filters_preserved_and_sql_aggregates_after_stable_union(self):
        result, diagnostics, session = self.execute(self.rule_book(), self.rules(), max_values=2)
        self.assertEqual(len(session.requests), 2)
        self.assertEqual(diagnostics["steps"][0]["rows"], 3)
        row = result["result"]["rows"][0]
        self.assertEqual((row["n"], row["kinds"], row["avg_weight"]), (3, 2, 6.0))
        for request in session.requests:
            self.assertEqual(request["constraints"][1], {"simple": {"name": "direction", "operator": "equal", "value": "ingress"}, "logOp": "and"})
            self.assertFalse(request["allow_redirects"])
            self.assertGreater(request["timeout"], 0)
            self.assertLessEqual(request["timeout"], 5)

    def test_conflicting_or_missing_stable_key_cannot_yield_partial_sql(self):
        for mode, reason in [("conflict", "conflicting_batch_record"), ("missing", "unverified_batch_merge_key")]:
            def responder(session, ci, query):
                if len(session.requests) == 2:
                    row = {"id": "r1", "securityGroupId": "g1", "direction": "ingress", "protocol": "bad", "weight": 99}
                    if mode == "missing":
                        row.pop("id")
                    payload = {"objList": [row], "totalNum": 1, "totalPageNo": 1, "currentPage": 1, "pageSize": 10000}
                    return SimpleNamespace(status_code=200, json=lambda: payload)
            diagnostics = {}
            with self.subTest(mode=mode), self.assertRaisesRegex(system._APIPlanRefusal, reason):
                system._execute_bounded_api(self.rule_book(), diagnostics,
                                           session=MemorySession(self.rules(), responder), max_values=2)
            self.assertFalse(diagnostics["sql_executed"])

    def test_wire_limit_is_measured_on_prepared_request(self):
        ids = ["长中文-" + str(index) + "x"*80 for index in range(9)]
        item = book(call("HOST", ("id", "in", ids)), sql="SELECT COUNT(*) AS n FROM CLOUD_HOST")
        database = {"HOST": [{"id": value} for value in ids]}
        _, diagnostics, session = self.execute(item, database, request_line_limit=800)
        self.assertGreater(len(session.requests), 1)
        self.assertLessEqual(diagnostics["max_request_line_bytes"], 800)
        for request in session.requests:
            self.assertLessEqual(len(("GET " + urlsplit(request["url"]).path + "?" + urlsplit(request["url"]).query + " HTTP/1.1\r\n").encode()), 800)

    def test_unsplittable_or_batch_count_bound_prevents_all_http(self):
        for item, limits, reason in [
            (book(call("HOST", ("name", "equal", "x"*2000)), sql="SELECT id FROM CLOUD_HOST"),
             {"request_line_limit": 800}, "unsplittable_request_line"),
            (self.rule_book(), {"max_values": 1, "max_batches": 2}, "too_many_api_batches"),
        ]:
            session = MemorySession(self.database)
            with self.subTest(reason=reason), self.assertRaisesRegex(system._APIPlanRefusal, reason):
                system._execute_bounded_api(item, {}, session=session, **limits)
            self.assertEqual(session.requests, [])

    def test_unconsumed_batched_resource_does_not_claim_business_fix(self):
        item = book(call("SECURITY_GROUP"), call("SECURITY_GROUP_RULE", ("securityGroupId", "in", "{{id from step 1}}")),
                    sql="SELECT name FROM CLOUD_SECURITY_GROUP")
        database = {"SECURITY_GROUP": [{"id": "g1", "name": "a"}, {"id": "g2", "name": "b"}]}
        session = MemorySession(database)
        with self.assertRaisesRegex(system._APIPlanRefusal, "batched_resource_not_consumed_by_sql"):
            system._execute_bounded_api(item, {}, session=session, max_values=1)
        self.assertEqual([request["ci"] for request in session.requests], ["SECURITY_GROUP"])

    def test_http_error_and_bad_json_are_failures_not_empty_data(self):
        for response in [SimpleNamespace(status_code=500),
                         SimpleNamespace(status_code=200, json=Mock(side_effect=ValueError("bad json"))),
                         SimpleNamespace(status_code=200, json=lambda: {})]:
            session = MemorySession(self.database, lambda *args: response)
            diagnostics = {}
            with self.subTest(response=response), self.assertRaises((RuntimeError, ValueError)):
                system._execute_bounded_api(self.dependent(), diagnostics, session=session)
            self.assertEqual(len(session.requests), 1)
            self.assertFalse(diagnostics["sql_executed"])

    def test_complete_pagination_and_request_record_time_bounds(self):
        result, diagnostics, session = self.execute(book(call("HOST"), sql="SELECT COUNT(*) AS n FROM CLOUD_HOST"), page_size=1)
        self.assertEqual(result["result"]["rows"], [{"n": 2}])
        self.assertEqual(diagnostics["http_requests"], 2)
        for limits in [{"max_http_requests": 1}, {"max_records": 1}]:
            session = MemorySession(self.database)
            with self.subTest(limits=limits), self.assertRaises(RuntimeError):
                system._execute_bounded_api(self.dependent(), {}, session=session, **limits)
            self.assertEqual(len(session.requests), 1)
        clock = [0]
        def advance(*args):
            clock[0] = 20
        session = MemorySession(self.database, advance)
        with patch.object(system.time, "perf_counter", side_effect=lambda: clock[0]), self.assertRaises(RuntimeError):
            system._execute_bounded_api(self.dependent(), {}, session=session)
        self.assertEqual(len(session.requests), 1)

    def test_truncated_or_changing_pagination_is_failure(self):
        for mode in ["truncated", "changing"]:
            def responder(session, ci, query):
                page = int(query["pageNo"][0])
                if mode == "truncated" or page == 2:
                    payload = {"objList": [], "totalNum": 3 if mode == "changing" else 2,
                               "pageSize": 1, "totalPageNo": 3 if mode == "changing" else 2, "currentPage": page}
                    return SimpleNamespace(status_code=200, json=lambda: payload)
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                system._execute_bounded_api(self.dependent(), {}, session=MemorySession(self.database, responder), page_size=1)

    def test_missing_output_field_is_refusal_not_silent_empty_rows(self):
        item = book(call("HOST"), sql="SELECT absent_hostName FROM CLOUD_HOST")
        diagnostics = {}
        with self.assertRaisesRegex(system._APIPlanRefusal, "required_sql_field_unavailable"):
            system._execute_bounded_api(item, diagnostics, session=MemorySession(self.database))
        self.assertFalse(diagnostics["sql_executed"])

    def test_default_query_uses_original_execute_and_flag_defers_validation(self):
        query_system = system.RunbookQuerySystem.__new__(system.RunbookQuerySystem)
        query_system.items, query_system.retriever = [], None
        output = {"sql": JOIN_SQL, "result": {"rows": []}, "error": None}
        for enabled in ["0", "1"]:
            with self.subTest(enabled=enabled), patch.dict(os.environ, {"RUNBOOK_BOUNDED_API": enabled}), \
                    patch.object(system, "match_runbook", return_value=self.dependent()) as match, \
                    patch.object(system, "execute", return_value=output) as original, \
                    patch.object(system, "_execute_bounded_api", return_value=output) as bounded:
                self.assertIsNone(query_system.query("fixture question")["error"])
                self.assertEqual(original.call_count, int(enabled == "0"))
                self.assertEqual(bounded.call_count, int(enabled == "1"))
                self.assertEqual(match.call_args.kwargs, {"defer_api_validation": True} if enabled == "1" else {})


if __name__ == "__main__":
    unittest.main()
