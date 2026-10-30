"""Pure reference extracted from the reviewed matcher; test material, not a B adapter."""
import copy

_FAMILY_SPECS = {
    "F01": {"ci": "VM_NOVA", "table": "CLOUD_VM_NOVA",
            "filters": ["logicalRegionName", "tenantName", "vdcName", "azoneName", "status", "management"],
            "axes": {"group": ["none", "status", "azoneName", "management", "tenantName", "vdcName"],
                     "metrics": ["count", "total_active", "status_counts"],
                     "count_alias": ["count", "total"], "label": ["none", "ECS"],
                     "order": ["none", "count_desc"]}},
    "F08": {"ci": "HOST", "table": "CLOUD_HOST", "filters": ["logicalRegionName"],
            "axes": {"group": ["hypervisorType", "azoneName", "status"]}},
    "F14": {"ci": "VOLUME", "table": "CLOUD_VOLUME", "filters": ["logicalRegionName"],
            "axes": {"metrics": ["count_sum", "avg_max"]}},
    "F18": {"ci": "GAUSSDB_INSTANCE", "table": "CLOUD_GAUSSDB_INSTANCE",
            "filters": ["logicalRegionName"],
            "axes": {"group": ["flavorCode", "vdcName", "engineVersion", "haMode"],
                     "metrics": ["count", "count_storage"]}},
    "F20": {"ci": "NETWORK", "table": "CLOUD_NETWORK",
            "filters": ["shared", "providerNetworkType", "logicalRegionName"],
            "axes": {"view": ["rows", "count"], "count_alias": ["total", "count"]}},
    "F21": {"ci": "FLOATING_IPS", "table": "CLOUD_FLOATING_IPS",
            "filters": ["logicalRegionName"], "axes": {"group": ["vdcName", "tenantName_status"]}},
    "F27": {"ci": "OBS_BUCKET", "table": "CLOUD_OBS_BUCKET",
            "filters": ["logicalRegionName"],
            "axes": {"view": ["rows", "tenant_count"]}},
}

def _family_missing(value):
    return value is None or isinstance(value, str) and not value.strip()

def _materialize_family(item: dict, parameters: dict) -> dict:
    """Closed structural parameters -> ordinary api_call + sql, no old-ID routing.

    Call only after extraction and grounding. No entity defaults are consulted.
    Values False and 0 are not missing; field types are checked separately.
    """
    family = item.get("family_id")
    if family not in _FAMILY_SPECS or not isinstance(parameters, dict):
        raise ValueError("unknown_family_or_parameters")
    spec = _FAMILY_SPECS[family]
    if set(parameters) - (set(spec["axes"]) | {"scope", "filters", "required_filters"}):
        raise ValueError("unknown_structural_parameter")
    for axis, choices in spec["axes"].items():
        if axis in parameters and parameters[axis] not in choices:
            raise ValueError("invalid_axis:" + axis)

    filters = parameters.get("filters")
    required = parameters.get("required_filters")
    if (not isinstance(filters, dict) or not isinstance(required, list)
            or any(not isinstance(k, str) for k in required)
            or len(set(required)) != len(required)
            or set(required) != set(filters) or set(filters) - set(spec["filters"])):
        raise ValueError("invalid_filter_contract")
    for name, value in filters.items():
        if _family_missing(value):
            raise ValueError("missing_filter:" + name)
        if name in {"shared", "management"}:
            if type(value) is not bool:
                raise ValueError("boolean_required:" + name)
        elif not isinstance(value, str) or "{{" in value or "}}" in value:
            raise ValueError("text_required:" + name)
    scope = parameters.get("scope")
    if scope not in {"global", "filtered"}:
        raise ValueError("explicit_scope_required")
    if scope == "global" and filters or scope == "filtered" and not filters:
        raise ValueError("scope_filter_mismatch")
    if family not in {"F01", "F08"} and scope != "filtered":
        raise ValueError("filtered_scope_required")
    if family in {"F14", "F18", "F21", "F27"} or family == "F08" and scope == "filtered":
        if "logicalRegionName" not in filters:
            raise ValueError("region_required")
    if family == "F20" and "shared" not in filters:
        raise ValueError("shared_required")

    group = parameters.get("group", "vdcName" if family == "F14" else None)
    metrics = parameters.get("metrics", "count")
    alias = parameters.get("count_alias", "count")
    label = parameters.get("label", "none")
    order = parameters.get("order", "none")
    table = spec["table"]
    if family in {"F01", "F14", "F18"} and "metrics" not in parameters:
        raise ValueError("metric_required")
    if family == "F01":
        if group is None:
            raise ValueError("group_required")
        if metrics == "count":
            if group == "none" and alias != "total":
                raise ValueError("scalar_count_requires_total_alias")
            if alias == "total" and group != "none":
                raise ValueError("grouped_count_alias")
            if label == "ECS" and group != "vdcName":
                raise ValueError("label_requires_vdc")
            if order == "count_desc" and group == "none":
                raise ValueError("order_requires_group")
            select = ("'ECS' AS type, " if label == "ECS" else "")
            select += (group + ", " if group != "none" else "") + "COUNT(*) AS " + alias
        elif metrics == "total_active" and group == "vdcName":
            select = "vdcName, COUNT(*) AS total, SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_count"
        elif metrics == "status_counts" and group == "azoneName":
            select = ("azoneName, SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS running_count, "
                      "SUM(CASE WHEN status = 'stopped' THEN 1 ELSE 0 END) AS stopped_count, "
                      "SUM(CASE WHEN status NOT IN ('active', 'stopped', 'building') THEN 1 ELSE 0 END) AS error_count")
        else:
            raise ValueError("unreviewed_metric_group")
        if metrics != "count" and (label != "none" or order != "none" or alias != "count"):
            raise ValueError("unreviewed_metric_options")
    elif family == "F08":
        if group is None:
            raise ValueError("group_required")
        select = group + ", COUNT(*) AS count"
    elif family == "F14":
        if metrics == "count_sum":
            select = "vdcName, COUNT(*) AS count, SUM(size) AS total_size"
        elif metrics == "avg_max":
            select = "vdcName, AVG(size) AS avg_size, MAX(size) AS max_size"
        else:
            raise ValueError("metric_required")
    elif family == "F18":
        if group is None:
            raise ValueError("group_required")
        if metrics == "count" and group != "vdcName":
            select = group + ", COUNT(*) AS count"
        elif metrics == "count_storage" and group == "vdcName":
            select = "vdcName, COUNT(*) AS instance_count, SUM(dataVolumeSizeInGBs) AS total_storage"
        else:
            raise ValueError("unreviewed_metric_group")
    elif family == "F20":
        view = parameters.get("view")
        if view == "rows":
            if "count_alias" in parameters:
                raise ValueError("rows_has_no_count_alias")
            select = "name, providerNetworkType, providerPhysicalNetworkSegId"
        elif view == "count":
            if "count_alias" not in parameters:
                raise ValueError("explicit_count_alias_required")
            select = "COUNT(*) AS " + alias
        else:
            raise ValueError("view_required")
    elif family == "F21":
        if group is None:
            raise ValueError("group_required")
        group = "tenantName, status" if group == "tenantName_status" else group
        select = group + ", COUNT(*) AS count"

    elif family == "F27":
        view = parameters.get("view")
        if view == "rows":
            select = "name, bucketName, managedStatus"
            group = "none"
        elif view == "tenant_count":
            select = "tenantName, COUNT(*) AS count"
            group = "tenantName"
        else:
            raise ValueError("view_required")

    sql = "SELECT " + select + " FROM " + table
    if family != "F20" and group != "none":
        sql += " GROUP BY " + group
    if order == "count_desc":
        sql += " ORDER BY count DESC"
    call = {"method": "GET", "url": "/rest/hackthon/db/instances/" + spec["ci"] + "?pageNo=1&pageSize=10000"}
    if filters:
        call["condition"] = {"constraint": [
            {"simple": {"name": name, "value": value, "operator": "equal"}}
            for name, value in filters.items()]}
    ordinary = copy.deepcopy(item)
    ordinary.pop("family_id", None)
    ordinary.pop("default_params", None)
    ordinary["api_call"] = call
    ordinary["sql"] = sql
    return ordinary
