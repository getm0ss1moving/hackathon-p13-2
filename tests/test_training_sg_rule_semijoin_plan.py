"""Closed-profile counterexamples and SQLite equivalence; no HTTP/model/data files."""
import copy
import json
from pathlib import Path
import socket
import sqlite3
import sys
import unittest
from unittest.mock import patch

from runbook_sg_rule_semijoin import plan_security_group_rule_semijoin as plan


SCHEMA = {"SECURITY_GROUP": ["id", "name", "regionId"],
          "SECURITY_GROUP_RULE": ["id", "securityGroupId", "name", "protocol"]}
MAP = {"SECURITY_GROUP": "CLOUD_SECURITY_GROUP", "SECURITY_GROUP_RULE": "CLOUD_SECURITY_GROUP_RULE"}
SQL = ("SELECT g.id AS sg_id, g.name AS sg_name, COUNT(r.id) AS rule_count "
       "FROM CLOUD_SECURITY_GROUP AS g INNER JOIN CLOUD_SECURITY_GROUP_RULE AS r "
       "ON g.id=r.securityGroupId GROUP BY g.id,g.name ORDER BY sg_id")


def fixture(sql=SQL, *, explicit_child=False):
    calls = [{"method": "GET", "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000"}]
    if explicit_child:
        calls.append({"method": "GET", "url": "/rest/hackthon/db/instances/SECURITY_GROUP_RULE"})
    return {"id": "synthetic-not-used", "name": "synthetic-not-used", "sql": sql,
            "api_call": calls, "arbitrary_metadata": {"preserve": True}}


def checked(item, **kwargs):
    return plan(item, schema_columns=kwargs.get("schema_columns", SCHEMA), ci_name_map=kwargs.get("ci_name_map", MAP))


def execute(sql, groups, rules, *, child_type="TEXT"):
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE CLOUD_SECURITY_GROUP(id TEXT,name TEXT,regionId TEXT)")
        connection.execute(f"CREATE TABLE CLOUD_SECURITY_GROUP_RULE(id TEXT,securityGroupId {child_type},name TEXT,protocol TEXT)")
        connection.executemany("INSERT INTO CLOUD_SECURITY_GROUP VALUES(?,?,?)", groups)
        connection.executemany("INSERT INTO CLOUD_SECURITY_GROUP_RULE VALUES(?,?,?,?)", rules)
        cursor = connection.execute(sql)
        return ([column[0] for column in cursor.description], cursor.fetchall())


class SemijoinProofTests(unittest.TestCase):
    def assertRefused(self, item):
        before = copy.deepcopy(item)
        result = checked(item)
        self.assertFalse(result["eligible"], result)
        self.assertNotIn("item", result)
        self.assertEqual(item, before)

    def test_missing_child_read_added_with_known_join_and_original_sql(self):
        source = fixture(); before = copy.deepcopy(source)
        result = checked(source)
        self.assertTrue(result["eligible"], result)
        self.assertEqual(result["proof"]["join_type"], "inner")
        self.assertEqual(result["item"]["sql"], source["sql"])
        self.assertEqual(result["item"]["api_call"][0], source["api_call"][0])
        self.assertEqual(result["item"]["api_call"][1]["condition"]["constraint"][0]["simple"],
                         {"name": "securityGroupId", "operator": "in", "value": "{{id from step 1}}"})
        self.assertEqual(source, before)

    def test_prepared_plan_is_reproved_and_idempotent(self):
        first = checked(fixture())["item"]; before = copy.deepcopy(first)
        again = checked(first)
        self.assertTrue(again["eligible"])
        self.assertTrue(again["proof"]["already_prepared"])
        self.assertEqual(again["item"], first)
        self.assertEqual(first, before)

    def test_unaliased_and_reverse_equality_are_supported(self):
        sql = ("SELECT CLOUD_SECURITY_GROUP.name AS sg_name,CLOUD_SECURITY_GROUP.id AS sg_id,"
               "COUNT(CLOUD_SECURITY_GROUP_RULE.id) AS rule_count FROM CLOUD_SECURITY_GROUP "
               "INNER JOIN CLOUD_SECURITY_GROUP_RULE ON CLOUD_SECURITY_GROUP_RULE.securityGroupId="
               "CLOUD_SECURITY_GROUP.id GROUP BY CLOUD_SECURITY_GROUP.name,CLOUD_SECURITY_GROUP.id;")
        self.assertTrue(checked(fixture(sql))["eligible"])

    def test_left_outer_keeps_zero_rule_parent_and_orphan_does_not_change_results(self):
        sql = SQL.replace("INNER JOIN", "LEFT OUTER JOIN")
        result = checked(fixture(sql));self.assertTrue(result["eligible"])
        self.assertEqual(result["proof"]["join_type"], "left")
        groups = [("g1", "alpha", "r1"), ("g2", "beta", "r1"), ("g3", "gamma", "r1")]
        rules = [("a", "g1", "a", "tcp"), ("b", "g1", "b", "udp"), ("c", "g2", "c", "tcp"),
                 ("orphan", "elsewhere", "x", "tcp"), ("null", None, "n", "tcp")]
        pushed = [row for row in rules if row[1] in {g[0] for g in groups}]
        baseline, actual = execute(sql, groups, rules), execute(sql, groups, pushed)
        self.assertEqual(actual, baseline)
        self.assertEqual(actual[1], [("g1", "alpha", 2), ("g2", "beta", 1), ("g3", "gamma", 0)])

    def test_inner_group_counts_and_duplicates_preserved(self):
        groups = [("g1", "alpha", "r1"), ("g1", "alpha", "r1"), ("g2", "beta", "r1")]
        rules = [("a", "g1", "a", "tcp"), ("b", "g1", "b", "tcp"), ("x", "outside", "x", "udp")]
        filtered = [row for row in rules if row[1] in {g[0] for g in groups}]
        self.assertEqual(execute(SQL, groups, filtered), execute(SQL, groups, rules))
        self.assertEqual(execute(SQL, groups, filtered)[1], [("g1", "alpha", 4)])

    def test_empty_root_count_executes_sql_and_is_one_zero_row_not_empty_rows(self):
        sql = "SELECT COUNT(*) AS total FROM CLOUD_SECURITY_GROUP g LEFT JOIN CLOUD_SECURITY_GROUP_RULE r ON g.id=r.securityGroupId"
        result = checked(fixture(sql));self.assertTrue(result["eligible"])
        self.assertEqual(result["proof"]["empty_root_policy"], "typed_empty_both_then_execute_original_sql")
        self.assertEqual(execute(sql, [], [ ("a", "g1", "a", "tcp") ])[1], [(0,)])
        self.assertEqual(execute(sql, [], [])[1], [(0,)])

    def test_empty_child_left_count_star_retains_parent_and_count_column_is_zero(self):
        sql = SQL.replace("INNER JOIN", "LEFT JOIN").replace("COUNT(r.id) AS rule_count", "COUNT(r.id) AS rule_count, COUNT(*) AS joined_count")
        self.assertTrue(checked(fixture(sql))["eligible"])
        self.assertEqual(execute(sql, [("g1", "alpha", "r1")], [])[1], [("g1", "alpha", 0, 1)])

    def test_parent_api_scope_preserved_exactly(self):
        item = fixture();item["api_call"][0]["condition"] = {"constraint": [
            {"simple": {"name": "regionId", "operator": "equal", "value": "region-variable"}},
            {"simple": {"name": "name", "operator": "contain", "value": "prefix-variable"}, "logOp": "and"}]}
        self.assertEqual(checked(item)["item"]["api_call"][0], item["api_call"][0])
        scoped = [("g1", "alpha", "selected")]
        all_rules = [("a", "g1", "a", "tcp"), ("b", "g2", "b", "tcp")]
        self.assertEqual(execute(SQL, scoped, all_rules), execute(SQL, scoped, all_rules[:1]))

    def test_explicit_unconditional_child_read_preserved_except_predicate(self):
        item = fixture(explicit_child=True);item["api_call"][1]["condition"]={"constraint":[]}
        result = checked(item);self.assertTrue(result["eligible"])
        self.assertEqual(result["item"]["api_call"][1]["url"], item["api_call"][1]["url"])

    def test_metadata_not_used_for_routing_and_not_modified(self):
        source=fixture();source.update(id="arbitrary-entity",name="arbitrary-name",examples=["completely different"],default_params={"name":"unrelated"})
        result=checked(source);self.assertTrue(result["eligible"])
        self.assertEqual({k:v for k,v in result["item"].items() if k!="api_call"},
                         {k:v for k,v in source.items() if k!="api_call"})

    def test_disallowed_join_kinds_and_reverse_preserved_side(self):
        for keyword in ("RIGHT JOIN", "FULL JOIN", "CROSS JOIN"):
            with self.subTest(keyword=keyword):self.assertRefused(fixture(SQL.replace("INNER JOIN",keyword)))
        reverse = "SELECT r.id FROM CLOUD_SECURITY_GROUP_RULE r LEFT JOIN CLOUD_SECURITY_GROUP g ON g.id=r.securityGroupId"
        self.assertRefused(fixture(reverse))

    def test_or_and_additional_on_predicates_rejected(self):
        for extra in (" OR g.name=r.name", " AND g.name=r.name", " OR 1=1"):
            self.assertRefused(fixture(SQL.replace(" GROUP BY",extra+" GROUP BY")))

    def test_wrong_existing_join_fields_and_missing_relation_not_guessed(self):
        for replacement in ("g.name=r.name", "g.id=r.id", "g.regionId=r.securityGroupId", "g.id=r.securityGroupId COLLATE NOCASE"):
            self.assertRefused(fixture(SQL.replace("g.id=r.securityGroupId",replacement)))

    def test_extra_join_subquery_union_or_independent_rule_consumer_rejected(self):
        sqls = [SQL + " UNION ALL " + SQL,
                SQL.replace("g.id AS sg_id", "(SELECT COUNT(*) FROM CLOUD_SECURITY_GROUP_RULE) AS independent_count"),
                SQL.replace(" GROUP BY", " JOIN CLOUD_SECURITY_GROUP_RULE x ON x.id=r.id GROUP BY"),
                SQL.replace("CLOUD_SECURITY_GROUP AS g", "(SELECT * FROM CLOUD_SECURITY_GROUP) AS g"),
                "WITH q AS (SELECT * FROM CLOUD_SECURITY_GROUP_RULE) " + SQL]
        for sql in sqls:
            with self.subTest(sql=sql):self.assertRefused(fixture(sql))

    def test_where_having_or_additional_statement_not_supported(self):
        for sql in (SQL+";SELECT * FROM CLOUD_SECURITY_GROUP_RULE", SQL.replace(" GROUP BY"," WHERE r.id IS NULL GROUP BY"),
                    SQL.replace(" ORDER BY"," HAVING COUNT(r.id)>1 ORDER BY")):
            self.assertRefused(fixture(sql))

    def test_alias_collisions_and_spoofing_rejected(self):
        for sql in (SQL.replace(" AS r "," AS g "), SQL.replace(" AS g "," AS r "),
                    SQL.replace(" AS g "," AS CLOUD_SECURITY_GROUP_RULE "),
                    SQL.replace("g.id AS sg_id","ghost.id AS sg_id"), SQL.replace(" AS rule_count"," AS count")):
            self.assertRefused(fixture(sql))

    def test_quoted_comments_literals_and_unknown_field_rejected(self):
        for sql in (SQL.replace("g.id AS sg_id", '"g".id AS sg_id'),SQL+" --comment",SQL+" /*comment*/",
                    SQL.replace("g.name AS sg_name","'literal' AS sg_name"),SQL.replace("g.name AS sg_name","g.missing AS sg_name")):
            self.assertRefused(fixture(sql))

    def test_count_distinct_star_invalid_rejected_and_distinct_known_field_allowed(self):
        self.assertRefused(fixture(SQL.replace("COUNT(r.id)","COUNT(DISTINCT *)")))
        self.assertTrue(checked(fixture(SQL.replace("COUNT(r.id)","COUNT(DISTINCT r.id)")))["eligible"])

    def test_limit_and_offset_rejected_even_when_ordered(self):
        for suffix in (" LIMIT 1", " LIMIT 2 OFFSET 1", " OFFSET 1"):
            self.assertRefused(fixture(SQL+suffix))
        # ORDER BY a nonunique attribute may leave tied rows in batch order;
        # truncating that order can select another otherwise-correct object.
        tied = "SELECT g.id AS sg_id,r.id AS rule_id FROM CLOUD_SECURITY_GROUP g JOIN CLOUD_SECURITY_GROUP_RULE r ON g.id=r.securityGroupId ORDER BY g.name LIMIT 1"
        self.assertRefused(fixture(tied))

    def test_bare_aggregate_columns_and_bare_grouped_columns_rejected(self):
        sqls = [SQL.replace(" GROUP BY g.id,g.name", ""),
                SQL.replace("GROUP BY g.id,g.name", "GROUP BY g.id"),
                SQL.replace("COUNT(r.id) AS rule_count", "r.protocol AS protocol")]
        for sql in sqls:self.assertRefused(fixture(sql))
        # This is a logical group-key check: projection and GROUP tokens may
        # differ in case or whitespace while referring to the same known column.
        equivalent = SQL.replace("GROUP BY g.id,g.name", "GROUP BY G . ID, G . NAME")
        self.assertTrue(checked(fixture(equivalent))["eligible"])

    def test_child_nonkey_fields_not_supported_even_when_known_in_schema(self):
        schema={**SCHEMA,"SECURITY_GROUP_RULE":[*SCHEMA["SECURITY_GROUP_RULE"],"weight"]}
        sqls=[SQL.replace("COUNT(r.id)","COUNT(DISTINCT r.weight)"),
              SQL.replace("g.name AS sg_name","r.protocol AS protocol").replace("GROUP BY g.id,g.name","GROUP BY g.id,r.protocol"),
              SQL.replace("ORDER BY sg_id","ORDER BY r.protocol"),
              "SELECT r.protocol FROM CLOUD_SECURITY_GROUP g JOIN CLOUD_SECURITY_GROUP_RULE r ON g.id=r.securityGroupId",
              SQL.replace("GROUP BY g.id,g.name","GROUP BY g.id,g.name,r.protocol")]
        for sql in sqls:
            with self.subTest(sql=sql):self.assertFalse(checked(fixture(sql),schema_columns=schema)["eligible"])

    def test_schema_or_ci_mapping_missing_proof_rejected(self):
        for kwargs in ({"schema_columns":{}},{"schema_columns":{**SCHEMA,"SECURITY_GROUP_RULE":["id"]}},
                       {"schema_columns":{**SCHEMA,"SECURITY_GROUP_RULE":["securityGroupId"]}},
                       {"ci_name_map":{**MAP,"SECURITY_GROUP_RULE":"other"}}):
            self.assertFalse(checked(fixture(),**kwargs)["eligible"])

    def test_other_api_extra_steps_and_repeated_ci_rejected(self):
        for ci in ("ROUTER","SECURITY_GROUP"):
            item=fixture(explicit_child=True);item["api_call"][1]["url"]="/rest/hackthon/db/instances/"+ci
            self.assertRefused(item)
        item=fixture(explicit_child=True);item["api_call"].append(copy.deepcopy(item["api_call"][1]));self.assertRefused(item)

    def test_hidden_url_scope_partial_page_and_nonget_rejected(self):
        for suffix in ("?condition=hidden","?pageNo=2","?pageNo=1&pageNo=1","?pageSize=10001","#hidden"):
            item=fixture();item["api_call"][0]["url"]="/rest/hackthon/db/instances/SECURITY_GROUP"+suffix;self.assertRefused(item)
        for changes in ({"method":"POST"},{"autoPagination":False},{"headers":{"x":"y"}},
                        {"url":"https://other/rest/hackthon/db/instances/SECURITY_GROUP"}):
            item=fixture();item["api_call"][0].update(changes);self.assertRefused(item)

    def test_parent_or_unfilled_unknown_condition_rejected(self):
        for simple in ({"name":"name","value":"{{name}}"},{"name":"not_a_field","value":"value"},
                       {"name":"id","operator":"in","value":[]},{"name":"name","value":True}):
            item=fixture();item["api_call"][0]["condition"]={"constraint":[{"simple":simple}]};self.assertRefused(item)
        item=fixture();item["api_call"][0]["condition"]={"constraint":[{"simple":{"name":"id","value":"g1"},"logOp":"or"}]};self.assertRefused(item)

    def test_existing_child_filter_wrong_or_nonadjacent_dependency_not_rewritten(self):
        for simple in ({"name":"protocol","operator":"equal","value":"tcp"},
                       {"name":"securityGroupId","operator":"equal","value":"{{id from step 1}}"},
                       {"name":"securityGroupId","operator":"in","value":"{{id from step 2}}"}):
            item=fixture(explicit_child=True);item["api_call"][1]["condition"]={"constraint":[{"simple":simple}]};self.assertRefused(item)

    def test_prepared_plan_is_not_a_bypass_for_changed_sql_or_mapping(self):
        prepared=checked(fixture())["item"];prepared["sql"] = prepared["sql"].replace("g.id=r.securityGroupId","g.id=r.id")
        self.assertRefused(prepared)

    def test_numeric_affinity_counterexample_requires_runtime_string_key_contract(self):
        # Parent raw Python str '01' creates TEXT. Child raw Python int 1 creates
        # INTEGER in the original executor; SQLite applies numeric affinity at
        # JOIN, while server TEXT IN('01') excludes its stored text '1'.
        groups=[("01","alpha","r")];rules=[("a",1,"a","tcp")]
        self.assertEqual(execute(SQL,groups,rules,child_type="INTEGER")[1],[("01","alpha",1)])
        exact_server_text_filter=[row for row in rules if str(row[1]) in {g[0] for g in groups}]
        self.assertEqual(execute(SQL,groups,exact_server_text_filter,child_type="INTEGER")[1],[])
        self.assertIn("scalar_string_join_keys_no_sql_affinity_coercion", checked(fixture())["proof"]["runtime_obligations"])


if __name__ == "__main__":
    attempts=[]
    def blocked(*args,**kwargs):
        attempts.append(True)
        raise AssertionError("network forbidden")
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SemijoinProofTests)
    with patch.object(socket.socket,"connect",blocked),patch.object(socket,"create_connection",blocked):
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    receipt={"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
             "skips":len(result.skipped),"socket_attempts":len(attempts),"success":result.wasSuccessful()}
    Path(__file__).with_name("test_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    raise SystemExit(not result.wasSuccessful())
