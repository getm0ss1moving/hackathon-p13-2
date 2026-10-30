# 独立ASCII实体原子与筛选边界复审

结论：**PASS**，独立 16 项中 16 通过、0 失败；80 个用例断言及 6 个静态检查，分别 0 / 0 失败。期望支持 8、拒绝 8；实际支持 8、拒绝 8。

## 哈希与改动范围

- 当前候选实测：`04098b713541a87681e0e916f84ccb4d82644ee218a68e424587c1cd3ced6576`。
- 固定 source 实测：`fc71c51f346c3ebf0b09911bc030bb40c1ba0547f25cdf6bf8d75b3b8a6bb506`。

两者均与指定哈希一致，前后读文件哈希不变。实际执行的是计算过哈希的源码 bytes，避免读取与导入间换版造成混淆。AST 对照只发现既有 `_filters` 改变，新增 `_inside_ascii_atom`；其他顶层定义、参数 schema、投影和物化代码保持相同。只新增本脚本、JSON 与本报告，没有修改源码、他人用例、170或早批冻结文件。

## 43921版本实际发现的回归

旧候选 `43921c34132f92833b016651fde9777d3ff45f8a26caa1e6d87909b891f4729b` 仍在磁盘时，独立实际执行了两个探针，并与 source 对照：

1. `查询区域r-main且AZ:zone-blue下vCPU分配率最高前3台宿主机`：source保留region/AZ两条件并物化，43921返回None，原因为 `ambiguous_unquoted_multi_value`。
2. `查询区域r-main且vendorName:ven-blue下各可用区存储池容量使用情况`：source保留region/vendor两条件并物化，43921同样错误拒绝。

这两条旧失败的原问题、参数、实际API及诊断保存在 JSON 的 `actual_initial_failure_evidence`。发现后立即报告主线程：初版把中文“且”后新ASCII原子起点的角色前缀也当成实体内部，误伤真实第二条件。没有对已替换的43921补跑或虚构旧16项总成绩。主线程修复为仅保护起点严格位于原子内部的命中；以下16项是对当前 `04098b713541a87681e0e916f84ccb4d82644ee218a68e424587c1cd3ced6576` 的真实运行。

## 独立16项结果

| 新用例 | 期望 | 当前候选 | source对照 | 结论 | 诊断/核验 |
|---|---|---|---|---|---|
| P01_embedded_roles_resources_many_separators | 支持 | 物化 | None | PASS | 完整API条件/原SQL/输入不变检查通过 |
| P02_cross_role_values_chinese_connector | 支持 | 物化 | None | PASS | 完整API条件/原SQL/输入不变检查通过 |
| P03_comma_separated_second_ascii_role | 支持 | 物化 | None | PASS | 完整API条件/原SQL/输入不变检查通过 |
| P04_vendor_atom_with_grouping_role | 支持 | 物化 | None | PASS | 完整API条件/原SQL/输入不变检查通过 |
| P05_spaced_AND_real_second_role | 支持 | 物化 | None | PASS | 完整API条件/原SQL/输入不变检查通过 |
| P06_quoted_OR_negation_roles_opaque | 支持 | 物化 | 物化 | PASS | 完整API条件/原SQL/输入不变检查通过 |
| P07_real_AZ_after_chinese_AND | 支持 | 物化 | 物化 | PASS | 完整API条件/原SQL/输入不变检查通过 |
| P08_real_vendor_after_chinese_AND | 支持 | 物化 | 物化 | PASS | 完整API条件/原SQL/输入不变检查通过 |
| N09_real_second_condition_omitted | None | None | None | PASS | parsed_parameters_do_not_match_question |
| N10_real_second_condition_wrong_value | None | None | None | PASS | parsed_parameters_do_not_match_question |
| N11_real_OR_outside_atoms | None | None | None | PASS | unconsumed_request_semantics |
| N12_real_negation_second_AZ | None | None | None | PASS | unsupported_filter_operator |
| N13_duplicate_region_after_atom | None | None | None | PASS | repeated_filter_role |
| N14_unrepresented_unknown_status_condition | None | None | None | PASS | unconsumed_request_semantics |
| N15_extra_output_column | None | None | None | PASS | unsupported_explicit_projection |
| N16_wrong_output_column_order | None | None | None | PASS | projection_order_or_columns_mismatch |

P01–P05 覆盖跨角色的原子内部词、`- : / @ + # . _` 分隔、中文连接词/逗号/空格/AND后的真实第二角色，以及真实分组角色。P06 区分引用内OR/否定/角色/资源字面值。P07/P08 是原先真实回归的固定复验。N09/N10 分别省略、错填真实第二条件，要求返回None；N11–N14检查原子外OR、不等于、重复角色和未表达的未知status条件；N15/N16使用原有“输出”语法检查额外列和错误列顺序，未假定支持“依次输出”。

每个支持项都核对原文值恰进入API一次，所有真实条件和顺序完整，资源/URL正确，SQL列/公式/排序完全等于独立期望；每个拒绝项都要求None及unsupported诊断，不把异常当作成功拒绝。source对照是同样16项的实际观察，不替代独立期望，也不改历史题组成绩。

## 边界

- 这是指定新哈希的16个有限独立组合，不证明任意自然语言，不扩大既有语法或参数schema。
- 原51、OPEN4、新24及旧70/41/82/24/46均未读取或运行；历史47/51不改，本报告不替这些题组作新成绩声明。
- 仅prepare_single_table_candidate及普通API/SQL物化的离线核验；无模型、SDK、服务、数据库执行、200题或正式总分。

## 复现

```sh
python3 a-family-implementation/batch4/parser-r2/scripts/independent_parser_review.py
python3 a-family-implementation/batch4/parser-r2/scripts/independent_parser_review.py --check
```

默认只写JSON和本报告；`--check`重算并比对保存产物，不写文件。两个源码文件哈希不符时不执行它们，报告检查失败。脚本禁用字节码缓存写入。
