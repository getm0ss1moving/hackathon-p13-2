RUNBOOK_ITEMS = [
  {
    "id": "rb_001",
    "name": "tpl_001_CMDB-001",
    "description": "当前所有ECS实例按状态的分布情况",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "当前所有ECS实例按状态的分布情况"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT status, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY status"
  },
  {
    "id": "rb_002",
    "name": "tpl_002_CMDB-004",
    "description": "查询区域region_guian4下所有ECS实例按状态的分布情况",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下所有ECS实例按状态的分布情况"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT status, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY status",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_003",
    "name": "tpl_003_CMDB-005",
    "description": "查询区域region_guian4下各可用区的ECS数量",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各可用区的ECS数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT azoneName, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY azoneName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_004",
    "name": "tpl_004_CMDB-010",
    "description": "查询租户AdvanceService_System_VDC在区域region_guian4可用区az0.dc0中的ECS",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC在区域region_guian4可用区az0.dc0中的ECS有多少台"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "tenantName",
              "value": "{{tenantName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC",
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_005",
    "name": "tpl_005_CMDB-011",
    "description": "区域region_guian4下管理虚拟机和租户虚拟机分别有多少",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "区域region_guian4下管理虚拟机和租户虚拟机分别有多少"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT management, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY management",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_006",
    "name": "tpl_006_CMDB-012",
    "description": "az0.dc0里正在跑的ECS有哪些IP，分别属于哪个租户",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "az0.dc0里正在跑的ECS有哪些IP，分别属于哪个租户"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "status",
              "value": "{{status}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, privateIps, tenantName FROM CLOUD_VM_NOVA",
    "default_params": {
      "azoneName": "az0.dc0",
      "status": "active"
    }
  },
  {
    "id": "rb_007",
    "name": "tpl_007_CMDB-013",
    "description": "查询区域region_guian4下各租户的ECS数量分布",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各租户的ECS数量分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT tenantName, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY tenantName ORDER BY count DESC",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_008",
    "name": "tpl_008_CMDB-017",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1的状态和规格",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1的状态和规格"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.status, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_009",
    "name": "tpl_009_CMDB-019",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1的创建时间",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1的创建时间"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, createdAt FROM CLOUD_VM_NOVA",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_010",
    "name": "tpl_010_CMDB-020",
    "description": "查询租户AdvanceService_System_VDC在区域region_guian4中的ECS实例名、规格和状态",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC在区域region_guian4中的ECS实例名、规格和状态"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.status, CLOUD_FLAVOR.name AS flavor_name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_011",
    "name": "tpl_011_CMDB-021",
    "description": "查询ECS实例中使用最多的前10种规格",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询ECS实例中使用最多的前10种规格"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_FLAVOR.name AS flavor_name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize, COUNT(*) AS count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id GROUP BY CLOUD_FLAVOR.name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize ORDER BY count DESC LIMIT 10"
  },
  {
    "id": "rb_012",
    "name": "tpl_012_CMDB-022",
    "description": "查询区域region_guian4下ECS实例中使用最多的前10种规格",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询区域region_guian4下ECS实例中使用最多的前10种规格"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_FLAVOR.name AS flavor_name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize, COUNT(*) AS count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id GROUP BY CLOUD_FLAVOR.name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize ORDER BY count DESC LIMIT 10",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_013",
    "name": "tpl_013_CMDB-023",
    "description": "ECS的规格配置是怎样的，1核2G的虚拟机有几台",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "ECS的规格配置是怎样的，1核2G的虚拟机有几台"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize, COUNT(*) AS count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id GROUP BY CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, CLOUD_FLAVOR.diskSize"
  },
  {
    "id": "rb_014",
    "name": "tpl_014_CMDB-024",
    "description": "规格为ManageOne-AutoOps的ECS实例目前有多少台",
    "resources": [
      "FLAVOR",
      "VM_NOVA"
    ],
    "examples": [
      "规格为ManageOne-AutoOps的ECS实例目前有多少台"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "flavorId",
                "value": "{{id from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id",
    "default_params": {
      "name": "ManageOne-AutoOps"
    }
  },
  {
    "id": "rb_015",
    "name": "tpl_015_CMDB-025",
    "description": "查询区域region_guian4下各租户的ECS规格分布，按租户分别展示",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询区域region_guian4下各租户的ECS规格分布，按租户分别展示"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT tenantName, CLOUD_FLAVOR.name AS flavor_name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize, COUNT(*) AS count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id GROUP BY tenantName, CLOUD_FLAVOR.name, CLOUD_FLAVOR.vcpuSize, CLOUD_FLAVOR.ramSize",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_016",
    "name": "tpl_016_CMDB-026",
    "description": "查询租户AdvanceService_System_VDC在区域region_guian4各可用区中的ECS实例名、规格",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC在区域region_guian4各可用区中的ECS实例名、规格和状态"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT azoneName, CLOUD_VM_NOVA.name AS vm_name, CLOUD_FLAVOR.name AS flavor_name, CLOUD_VM_NOVA.status FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id ORDER BY azoneName",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_017",
    "name": "tpl_017_CMDB-027",
    "description": "查询区域region_guian4下各VDC的ECS数量和运行中ECS数量",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的ECS数量和运行中ECS数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS total, SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_count FROM CLOUD_VM_NOVA GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_018",
    "name": "tpl_018_CMDB-028",
    "description": "查询区域region_guian4下各可用区中异常状态ECS的实例名、IP、所属租户和宿主机名",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各可用区中异常状态ECS的实例名、IP、所属租户和宿主机名"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "status",
              "value": "{{status}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.azoneName, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps, CLOUD_VM_NOVA.tenantName, CLOUD_HOST.name AS host_name FROM CLOUD_VM_NOVA INNER JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id ORDER BY CLOUD_VM_NOVA.azoneName",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "status": "stopped"
    }
  },
  {
    "id": "rb_019",
    "name": "tpl_019_CMDB-029",
    "description": "查询区域region_guian4各租户的业务实例有哪些，要实例名、类型和IP",
    "resources": [
      "VM_NOVA",
      "VOLUME",
      "ELB"
    ],
    "examples": [
      "查询区域region_guian4各租户的业务实例有哪些，要实例名、类型和IP"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT tenantName, name AS instance_name, 'ECS' AS type, privateIps AS ip FROM CLOUD_VM_NOVA UNION ALL SELECT tenantName, name AS instance_name, 'Volume' AS type, '' AS ip FROM CLOUD_VOLUME UNION ALL SELECT tenantName, name AS instance_name, 'ELB' AS type, ip AS ip FROM CLOUD_ELB",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_020",
    "name": "tpl_020_CMDB-030",
    "description": "@dda96bcd@18718925@这个IP是哪台虚拟机的，它跑在哪台宿主机上",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "@dda96bcd@18718925@这个IP是哪台虚拟机的，它跑在哪台宿主机上"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "privateIps",
              "value": "{{privateIps}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps, CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS host_ip FROM CLOUD_VM_NOVA INNER JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id",
    "default_params": {
      "privateIps": "@dda96bcd@18718925@"
    }
  },
  {
    "id": "rb_021",
    "name": "tpl_021_CMDB-033",
    "description": "54098a30这个IP是哪台弹性IP，绑定了哪台ECS",
    "resources": [
      "FLOATING_IPS",
      "VM_NOVA"
    ],
    "examples": [
      "54098a30这个IP是哪台弹性IP，绑定了哪台ECS"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "fixedIpAddress",
                "value": "{{fixedIpAddress}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "privateIps",
                "value": "{{fixedIpAddress from step 1}}",
                "operator": "contain"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_FLOATING_IPS.floatingIpAddress AS floating_ip, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps FROM CLOUD_FLOATING_IPS INNER JOIN CLOUD_VM_NOVA ON CLOUD_FLOATING_IPS.fixedIpAddress = CLOUD_VM_NOVA.privateIps",
    "default_params": {
      "fixedIpAddress": "54098a30"
    }
  },
  {
    "id": "rb_022",
    "name": "tpl_022_CMDB-034",
    "description": "查询部署节点IPbba98a99对应的部署节点名称和所属云服务",
    "resources": [
      "S_DeployNode"
    ],
    "examples": [
      "查询部署节点IPbba98a99对应的部署节点名称和所属云服务"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_DeployNode?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "mgmtIp",
              "value": "{{mgmtIp}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT SYS_DeployNode.name AS node_name, SYS_DeployNode.mgmtIp AS node_ip, SYS_CloudService.name AS cloud_service_name FROM SYS_DeployNode INNER JOIN SYS_DeployInstance ON SYS_DeployNode.id = SYS_DeployInstance.deployNodeId INNER JOIN SYS_DeployComponent ON SYS_DeployInstance.deployComponentId = SYS_DeployComponent.id INNER JOIN SYS_Service ON SYS_DeployComponent.serviceId = SYS_Service.id INNER JOIN SYS_CloudService ON SYS_Service.cloudServiceId = SYS_CloudService.id",
    "default_params": {
      "mgmtIp": "bba98a99"
    }
  },
  {
    "id": "rb_023",
    "name": "tpl_023_CMDB-036",
    "description": "宿主机kvm-10上目前有多少台处于ACTIVE状态的虚拟机",
    "resources": [
      "HOST",
      "VM_NOVA"
    ],
    "examples": [
      "宿主机kvm-10上目前有多少台处于ACTIVE状态的虚拟机"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "hostId",
                "value": "{{id from step 1}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "status",
                "value": "{{status}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS total FROM CLOUD_VM_NOVA",
    "default_params": {
      "name": "kvm-10",
      "status": "active"
    }
  },
  {
    "id": "rb_024",
    "name": "tpl_024_CMDB-039",
    "description": "kvm_group1集群下宿主机和虚拟机的对应关系",
    "resources": [
      "CLUSTER"
    ],
    "examples": [
      "kvm_group1集群下宿主机和虚拟机的对应关系"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_HOST.name AS host_name, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.status, CLOUD_VM_NOVA.privateIps FROM CLOUD_CLUSTER INNER JOIN M_ClusterContainsPhyHost ON CLOUD_CLUSTER.id = M_ClusterContainsPhyHost.source_Instance_Id INNER JOIN CLOUD_HOST ON M_ClusterContainsPhyHost.target_Instance_Id = CLOUD_HOST.id INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId",
    "default_params": {
      "name": "kvm_group1"
    }
  },
  {
    "id": "rb_025",
    "name": "tpl_025_CMDB-040",
    "description": "kvm_group1集群下有多少台宿主机，每台宿主机上跑了多少虚拟机",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "kvm_group1集群下有多少台宿主机，每台宿主机上跑了多少虚拟机"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "clusterName",
              "value": "{{clusterName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress, COUNT(CLOUD_VM_NOVA.id) AS vm_count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id GROUP BY CLOUD_HOST.name, CLOUD_HOST.ipAddress",
    "default_params": {
      "clusterName": "kvm_group1"
    }
  },
  {
    "id": "rb_026",
    "name": "tpl_026_CMDB-041",
    "description": "查询宿主机kvm-10上ECS按状态分布",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询宿主机kvm-10上ECS按状态分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.status, COUNT(*) AS count FROM CLOUD_HOST INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId GROUP BY CLOUD_VM_NOVA.status",
    "default_params": {
      "name": "kvm-10"
    }
  },
  {
    "id": "rb_027",
    "name": "tpl_027_CMDB-042",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1的完整归属链（VM→宿主机",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1的完整归属链（VM→宿主机→物理机）"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS host_ip, SYS_X86Server.name AS server_name, SYS_X86Server.id AS server_id FROM CLOUD_VM_NOVA INNER JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id INNER JOIN SYS_X86Server ON CLOUD_HOST.serverId = SYS_X86Server.id",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_028",
    "name": "tpl_028_CMDB-043",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1跑在哪台宿主机上",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1跑在哪台宿主机上"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS host_ip FROM CLOUD_VM_NOVA INNER JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_029",
    "name": "tpl_029_CMDB-044",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1属于哪个集群、哪个可用区",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1属于哪个集群、哪个可用区"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, clusterName, azoneName FROM CLOUD_VM_NOVA",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_030",
    "name": "tpl_030_CMDB-045",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1关联的镜像信息",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1关联的镜像信息"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_IMAGE.name AS image_name, CLOUD_IMAGE.osType AS os_type FROM CLOUD_VM_NOVA INNER JOIN M_VMUsesImage ON CLOUD_VM_NOVA.id = M_VMUsesImage.source_Instance_Id INNER JOIN CLOUD_IMAGE ON M_VMUsesImage.target_Instance_Id = CLOUD_IMAGE.id",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_031",
    "name": "tpl_031_CMDB-046",
    "description": "查询宿主机kvm-10关联的物理服务器CPU架构",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询宿主机kvm-10关联的物理服务器CPU架构"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_HOST.name AS host_name, SYS_X86Server.cpuModel, SYS_X86Server.manufacturer, SYS_X86Server.cpuArch FROM CLOUD_HOST INNER JOIN SYS_X86Server ON CLOUD_HOST.serverId = SYS_X86Server.id",
    "default_params": {
      "name": "kvm-10"
    }
  },
  {
    "id": "rb_032",
    "name": "tpl_032_CMDB-047",
    "description": "查询集群kvm_group1下所有宿主机列表及资源总量",
    "resources": [
      "CLUSTER"
    ],
    "examples": [
      "查询集群kvm_group1下所有宿主机列表及资源总量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress, CLOUD_HOST.totalVcpuCores, CLOUD_HOST.totalVmemoryMB FROM CLOUD_CLUSTER INNER JOIN M_ClusterContainsPhyHost ON CLOUD_CLUSTER.id = M_ClusterContainsPhyHost.source_Instance_Id INNER JOIN CLOUD_HOST ON M_ClusterContainsPhyHost.target_Instance_Id = CLOUD_HOST.id",
    "default_params": {
      "name": "kvm_group1"
    }
  },
  {
    "id": "rb_033",
    "name": "tpl_033_CMDB-048",
    "description": "集群kvm_group1下宿主机的IP和虚拟化类型，每台宿主机上跑了多少虚拟机",
    "resources": [
      "CLUSTER"
    ],
    "examples": [
      "集群kvm_group1下宿主机的IP和虚拟化类型，每台宿主机上跑了多少虚拟机"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress, CLOUD_HOST.hypervisorType, COUNT(CLOUD_VM_NOVA.id) AS vm_count FROM CLOUD_CLUSTER INNER JOIN M_ClusterContainsPhyHost ON CLOUD_CLUSTER.id = M_ClusterContainsPhyHost.source_Instance_Id INNER JOIN CLOUD_HOST ON M_ClusterContainsPhyHost.target_Instance_Id = CLOUD_HOST.id INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId GROUP BY CLOUD_HOST.name, CLOUD_HOST.ipAddress, CLOUD_HOST.hypervisorType",
    "default_params": {
      "name": "kvm_group1"
    }
  },
  {
    "id": "rb_034",
    "name": "tpl_034_CMDB-049",
    "description": "查询区域region_guian4可用区az0.dc0中各集群的宿主机数量、vCPU总量和运行中虚拟机数量",
    "resources": [
      "CLUSTER"
    ],
    "examples": [
      "查询区域region_guian4可用区az0.dc0中各集群的宿主机数量、vCPU总量和运行中虚拟机数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_CLUSTER.name AS cluster_name, COUNT(DISTINCT CLOUD_HOST.id) AS host_count, SUM(CLOUD_HOST.totalVcpuCores) AS total_vcpu, SUM(CASE WHEN CLOUD_VM_NOVA.status = 'active' THEN 1 ELSE 0 END) AS active_vm_count FROM CLOUD_CLUSTER INNER JOIN M_ClusterContainsPhyHost ON CLOUD_CLUSTER.id = M_ClusterContainsPhyHost.source_Instance_Id INNER JOIN CLOUD_HOST ON M_ClusterContainsPhyHost.target_Instance_Id = CLOUD_HOST.id INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId GROUP BY CLOUD_CLUSTER.name",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_035",
    "name": "tpl_035_CMDB-050",
    "description": "查询区域region_guian4可用区az0.dc0中集群kvm_group1下宿主机、VM及挂载云硬盘的端到端拓扑",
    "resources": [
      "CLUSTER"
    ],
    "examples": [
      "查询区域region_guian4可用区az0.dc0中集群kvm_group1下宿主机、VM及挂载云硬盘的端到端拓扑"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_CLUSTER.name AS cluster_name, CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS host_ip, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.status AS vm_status, CLOUD_VOLUME.name AS volume_name, CLOUD_VOLUME.size AS volume_size FROM CLOUD_CLUSTER INNER JOIN M_ClusterContainsPhyHost ON CLOUD_CLUSTER.id = M_ClusterContainsPhyHost.source_Instance_Id INNER JOIN CLOUD_HOST ON M_ClusterContainsPhyHost.target_Instance_Id = CLOUD_HOST.id INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VM_NOVA.id = R_VOLUME_MOUNTON_VM.vmId INNER JOIN CLOUD_VOLUME ON R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0",
      "name": "kvm_group1"
    }
  },
  {
    "id": "rb_036",
    "name": "tpl_036_CMDB-051",
    "description": "查询区域region_guian4下KVM虚拟化类型的集群有多少个，包含多少台宿主机",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4下KVM虚拟化类型的集群有多少个，包含多少台宿主机"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "hypervisorType",
              "value": "{{hypervisorType}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(DISTINCT CLOUD_CLUSTER.id) AS cluster_count, COUNT(DISTINCT CLOUD_HOST.id) AS host_count FROM CLOUD_HOST INNER JOIN M_ClusterContainsPhyHost ON CLOUD_HOST.id = M_ClusterContainsPhyHost.target_Instance_Id INNER JOIN CLOUD_CLUSTER ON M_ClusterContainsPhyHost.source_Instance_Id = CLOUD_CLUSTER.id",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "hypervisorType": "KVM"
    }
  },
  {
    "id": "rb_037",
    "name": "tpl_037_CMDB-052",
    "description": "查询租户AdvanceService_System_VDC在区域region_guian4中的ECS实例列表",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC在区域region_guian4中的ECS实例列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "tenantName",
              "value": "{{tenantName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, privateIps, status FROM CLOUD_VM_NOVA",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_038",
    "name": "tpl_038_CMDB-053",
    "description": "查询租户CodeArtsDeploy在区域region_guian4可用区az0.dc0中的ECS IP列表",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询租户CodeArtsDeploy在区域region_guian4可用区az0.dc0中的ECS IP列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "tenantName",
              "value": "{{tenantName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, privateIps, status FROM CLOUD_VM_NOVA",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC",
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_039",
    "name": "tpl_039_CMDB-055",
    "description": "查询区域region_guian4可用区az0.dc0中所有ECS的IP列表和租户归属",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4可用区az0.dc0中所有ECS的IP列表和租户归属"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, privateIps, tenantName FROM CLOUD_VM_NOVA",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_040",
    "name": "tpl_040_CMDB-056",
    "description": "查询区域region_guian4下各租户在各个可用区中的ECS实例名和IP",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各租户在各个可用区中的ECS实例名和IP"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.tenantName AS tenant_name, CLOUD_VM_NOVA.azoneName AS azone_name, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS private_ips FROM CLOUD_VM_NOVA",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_041",
    "name": "tpl_041_CMDB-057",
    "description": "查询区域region_guian4下关联了弹性IP的ECS实例名和固定IP",
    "resources": [
      "FLOATING_IPS",
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下关联了弹性IP的ECS实例名和固定IP"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "status",
                "value": "{{status}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "privateIps",
                "value": "{{fixedIpAddress from step 1}}",
                "operator": "contain"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS private_ips, CLOUD_FLOATING_IPS.floatingIpAddress AS floating_ip FROM CLOUD_FLOATING_IPS INNER JOIN CLOUD_VM_NOVA ON CLOUD_FLOATING_IPS.fixedIpAddress = CLOUD_VM_NOVA.privateIps",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "status": "active"
    }
  },
  {
    "id": "rb_042",
    "name": "tpl_042_CMDB-060",
    "description": "查询VDCpaas-aom在区域region_guian4可用区az0.dc0中各租户的ECS实例名和IP",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询VDCpaas-aom在区域region_guian4可用区az0.dc0中各租户的ECS实例名和IP"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "vdcName",
              "value": "{{vdcName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT tenantName, name, privateIps FROM CLOUD_VM_NOVA ORDER BY tenantName",
    "default_params": {
      "vdcName": "paas-aom",
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_043",
    "name": "tpl_043_CMDB-061",
    "description": "查询区域region_guian4下运行中的ECS实例名、IP和所属规格",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询区域region_guian4下运行中的ECS实例名、IP和所属规格"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "status",
                "value": "{{status}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS private_ips, CLOUD_FLAVOR.name AS flavor_name FROM CLOUD_VM_NOVA LEFT JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "status": "active"
    }
  },
  {
    "id": "rb_044",
    "name": "tpl_044_CMDB-066",
    "description": "查询区域region_guian4下各VDC的ECS数量",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的ECS数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT 'ECS' AS type, vdcName, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_045",
    "name": "tpl_045_CMDB-067",
    "description": "查询区域region_guian4下各VDC的ECS实例数量、云硬盘数量和云硬盘总容量",
    "resources": [
      "VM_NOVA",
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的ECS实例数量、云硬盘数量和云硬盘总容量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT a.vdcName, a.ecs_count, b.volume_count, b.total_volume_size FROM (SELECT vdcName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY vdcName) a LEFT JOIN (SELECT vdcName, COUNT(*) AS volume_count, SUM(size) AS total_volume_size FROM CLOUD_VOLUME GROUP BY vdcName) b ON a.vdcName = b.vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_046",
    "name": "tpl_046_CMDB-068",
    "description": "查询区域region_guian4下ECS数量、云硬盘数量和VPC数量",
    "resources": [
      "VM_NOVA",
      "VOLUME",
      "ROUTER"
    ],
    "examples": [
      "查询区域region_guian4下ECS数量、云硬盘数量和VPC数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT 'ECS' AS type, COUNT(*) AS count FROM CLOUD_VM_NOVA UNION ALL SELECT 'Volume' AS type, COUNT(*) AS count FROM CLOUD_VOLUME UNION ALL SELECT 'VPC' AS type, COUNT(*) AS count FROM CLOUD_ROUTER",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_047",
    "name": "tpl_047_CMDB-069",
    "description": "查询区域region_guian4所有VDC中各VDC的ECS数量、云硬盘数量和VPC数量",
    "resources": [
      "VM_NOVA",
      "VOLUME",
      "ROUTER"
    ],
    "examples": [
      "查询区域region_guian4所有VDC中各VDC的ECS数量、云硬盘数量和VPC数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT 'ECS' AS type, vdcName, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY vdcName UNION ALL SELECT 'Volume' AS type, vdcName, COUNT(*) AS count FROM CLOUD_VOLUME GROUP BY vdcName UNION ALL SELECT 'VPC' AS type, vdcName, COUNT(*) AS count FROM CLOUD_ROUTER GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_048",
    "name": "tpl_048_CMDB-071",
    "description": "帮我统计系统中各虚拟化类型的宿主机数量分布",
    "resources": [
      "HOST"
    ],
    "examples": [
      "帮我统计系统中各虚拟化类型的宿主机数量分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT hypervisorType, COUNT(*) AS count FROM CLOUD_HOST GROUP BY hypervisorType"
  },
  {
    "id": "rb_049",
    "name": "tpl_049_CMDB-073",
    "description": "查询区域region_guian4下各可用区的宿主机数量",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4下各可用区的宿主机数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT azoneName, COUNT(*) AS count FROM CLOUD_HOST GROUP BY azoneName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_050",
    "name": "tpl_050_CMDB-074",
    "description": "帮我查询可用区az0.dc0下宿主机的CPU架构分布情况",
    "resources": [
      "HOST"
    ],
    "examples": [
      "帮我查询可用区az0.dc0下宿主机的CPU架构分布情况"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT SYS_X86Server.cpuArch AS cpu_arch, COUNT(*) AS count FROM CLOUD_HOST INNER JOIN SYS_X86Server ON CLOUD_HOST.serverId = SYS_X86Server.id GROUP BY SYS_X86Server.cpuArch",
    "default_params": {
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_051",
    "name": "tpl_051_CMDB-075",
    "description": "查询区域region_guian4可用区az0.dc0下宿主机的CPU架构分布",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4可用区az0.dc0下宿主机的CPU架构分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT SYS_X86Server.cpuArch AS cpu_arch, COUNT(*) AS count FROM CLOUD_HOST INNER JOIN SYS_X86Server ON CLOUD_HOST.serverId = SYS_X86Server.id GROUP BY SYS_X86Server.cpuArch",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_052",
    "name": "tpl_052_CMDB-077",
    "description": "查询整个Region内部所有的物理服务器CPU架构类型并统计各类数量",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询整个Region内部所有的物理服务器CPU架构类型并统计各类数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT cpuArch, COUNT(*) AS count FROM SYS_X86Server GROUP BY cpuArch",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_053",
    "name": "tpl_053_CMDB-078",
    "description": "查询区域region_guian4下宿主机按状态分布",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4下宿主机按状态分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT status, COUNT(*) AS count FROM CLOUD_HOST GROUP BY status",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_054",
    "name": "tpl_054_CMDB-080",
    "description": "查询区域region_guian4下物理服务器CPU架构类型统计",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询区域region_guian4下物理服务器CPU架构类型统计"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT cpuArch, COUNT(*) AS count FROM SYS_X86Server GROUP BY cpuArch",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_055",
    "name": "tpl_055_CMDB-081",
    "description": "查询区域贵安4虚拟内所有物理服务器的CPU架构类型、所属可用区和关联宿主机上的虚拟机数量",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询区域贵安4虚拟内所有物理服务器的CPU架构类型、所属可用区和关联宿主机上的虚拟机数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT SYS_X86Server.cpuArch AS cpu_arch, CLOUD_HOST.azoneName AS azone_name, COUNT(CLOUD_VM_NOVA.id) AS vm_count FROM SYS_X86Server INNER JOIN CLOUD_HOST ON SYS_X86Server.id = CLOUD_HOST.serverId INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId GROUP BY SYS_X86Server.cpuArch, CLOUD_HOST.azoneName",
    "default_params": {
      "logicalRegionName": "贵安4虚拟"
    }
  },
  {
    "id": "rb_056",
    "name": "tpl_056_CMDB-084",
    "description": "查询区域region_guian4下vCPU分配率最高的前5台宿主机",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4下vCPU分配率最高的前5台宿主机"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, ipAddress, allocatedVcpuCores, totalVcpuCores, CAST(allocatedVcpuCores AS FLOAT) / totalVcpuCores AS allocation_rate FROM CLOUD_HOST ORDER BY allocation_rate DESC LIMIT 5",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_057",
    "name": "tpl_057_CMDB-085",
    "description": "查询可用区az0.dc0下内存剩余量最大的前3台宿主机",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询可用区az0.dc0下内存剩余量最大的前3台宿主机"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, ipAddress, totalVmemoryMB, allocatedVmemoryMB, totalVmemoryMB - allocatedVmemoryMB AS remaining_memory FROM CLOUD_HOST ORDER BY remaining_memory DESC LIMIT 3",
    "default_params": {
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_058",
    "name": "tpl_058_CMDB-086",
    "description": "查询区域region_guian4可用区az0.dc0中所有宿主机的主机名、IP、vCPU总量、已分配vCPU和CPU架",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4可用区az0.dc0中所有宿主机的主机名、IP、vCPU总量、已分配vCPU和CPU架构"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS ip_address, CLOUD_HOST.totalVcpuCores AS total_vcpu, CLOUD_HOST.allocatedVcpuCores AS allocated_vcpu, SYS_X86Server.cpuArch AS cpu_arch FROM CLOUD_HOST INNER JOIN SYS_X86Server ON CLOUD_HOST.serverId = SYS_X86Server.id",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_059",
    "name": "tpl_059_CMDB-087",
    "description": "查询宿主机9EAE8CF9-63F0-D196-EE11-C7830A72D98C的IP和资源配置，上面跑了多少虚拟机",
    "resources": [
      "HOST",
      "VM_NOVA"
    ],
    "examples": [
      "查询宿主机9EAE8CF9-63F0-D196-EE11-C7830A72D98C的IP和资源配置，上面跑了多少虚拟机"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "nativeId",
                "value": "{{nativeId}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "hostId",
                "value": "{{id from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS ip_address, CLOUD_HOST.totalCpu AS total_cpu, COUNT(CLOUD_VM_NOVA.id) AS vm_count FROM CLOUD_HOST INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId GROUP BY CLOUD_HOST.name, CLOUD_HOST.ipAddress, CLOUD_HOST.totalCpu",
    "default_params": {
      "nativeId": "9EAE8CF9-63F0-D196-EE11-C7830A72D98C"
    }
  },
  {
    "id": "rb_060",
    "name": "tpl_060_CMDB-088",
    "description": "查询区域region_guian4可用区az0.dc0中所有宿主机的主机名、IP、vCPU总量、已分配vCPU、CPU架",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4可用区az0.dc0中所有宿主机的主机名、IP、vCPU总量、已分配vCPU、CPU架构和运行中虚拟机列表"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "azoneName",
                "value": "{{azoneName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "azoneName",
                "value": "{{azoneName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "status",
                "value": "{{status}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS ip_address, CLOUD_HOST.totalVcpuCores AS total_vcpu, CLOUD_HOST.allocatedVcpuCores AS allocated_vcpu, SYS_X86Server.cpuArch AS cpu_arch, CLOUD_VM_NOVA.name AS vm_name FROM CLOUD_HOST INNER JOIN SYS_X86Server ON CLOUD_HOST.serverId = SYS_X86Server.id INNER JOIN CLOUD_VM_NOVA ON CLOUD_HOST.id = CLOUD_VM_NOVA.hostId",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "azoneName": "az0.dc0",
      "status": "normal"
    }
  },
  {
    "id": "rb_061",
    "name": "tpl_061_CMDB-089",
    "description": "查询部署节点APIGWLB-01_roma-guian-4的管理IP信息",
    "resources": [
      "S_DeployNode"
    ],
    "examples": [
      "查询部署节点APIGWLB-01_roma-guian-4的管理IP信息"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_DeployNode?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT name AS node_name, mgmtIp AS mgmt_ip FROM SYS_DeployNode",
    "default_params": {
      "name": "APIGWLB-01_roma-guian-4"
    }
  },
  {
    "id": "rb_062",
    "name": "tpl_062_CMDB-090",
    "description": "查询区域region_guian4下各VDC的管理虚拟机名称、IP和所属云服务",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的管理虚拟机名称、IP和所属云服务"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "management",
              "value": "{{management}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.vdcName AS vdc_name, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS private_ips, SYS_CloudService.indexName AS cloud_service_name FROM CLOUD_VM_NOVA INNER JOIN SYS_DeployNode ON CLOUD_VM_NOVA.id = SYS_DeployNode.vmId INNER JOIN SYS_DeployInstance ON SYS_DeployNode.id = SYS_DeployInstance.deployNodeId INNER JOIN SYS_DeployComponent ON SYS_DeployInstance.deployComponentId = SYS_DeployComponent.id INNER JOIN SYS_Service ON SYS_DeployComponent.serviceId = SYS_Service.id INNER JOIN SYS_CloudService ON SYS_Service.cloudServiceId = SYS_CloudService.id ORDER BY CLOUD_VM_NOVA.vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "management": "True"
    }
  },
  {
    "id": "rb_063",
    "name": "tpl_063_CMDB-091",
    "description": "查询型号为Atlas 800T A2的服务器数量及分布情况",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询型号为Atlas 800T A2的服务器数量及分布情况"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "productName",
              "value": "{{productName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT logicalRegionName, COUNT(*) AS count FROM SYS_X86Server GROUP BY logicalRegionName",
    "default_params": {
      "productName": "Atlas 800T A2"
    }
  },
  {
    "id": "rb_064",
    "name": "tpl_064_CMDB-092",
    "description": "查询厂商为Huawei的服务器列表，包括主机名、IP地址、CPU型号、CPU架构",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询厂商为Huawei的服务器列表，包括主机名、IP地址、CPU型号、CPU架构"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "manufacturer",
              "value": "{{manufacturer}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, ipAddress, cpuModel, cpuArch FROM SYS_X86Server",
    "default_params": {
      "manufacturer": "Huawei"
    }
  },
  {
    "id": "rb_065",
    "name": "tpl_065_CMDB-093",
    "description": "查询区域region_guian4下各厂商的物理服务器数量分布",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询区域region_guian4下各厂商的物理服务器数量分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT manufacturer, COUNT(*) AS count FROM SYS_X86Server GROUP BY manufacturer",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_066",
    "name": "tpl_066_CMDB-096",
    "description": "Huawei厂商的服务器在哪些区域分布最多",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "Huawei厂商的服务器在哪些区域分布最多"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "manufacturer",
              "value": "{{manufacturer}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT logicalRegionName, COUNT(*) AS count FROM SYS_X86Server GROUP BY logicalRegionName ORDER BY count DESC LIMIT 1",
    "default_params": {
      "manufacturer": "Huawei"
    }
  },
  {
    "id": "rb_067",
    "name": "tpl_067_CMDB-097",
    "description": "查询区域region_guian4下各集群中vCPU分配率超过80%的宿主机列表",
    "resources": [
      "HOST"
    ],
    "examples": [
      "查询区域region_guian4下各集群中vCPU分配率超过80%的宿主机列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_CLUSTER.name AS cluster_name, CLOUD_HOST.name AS host_name, CLOUD_HOST.ipAddress AS ip_address, CLOUD_HOST.allocatedVcpuCores, CLOUD_HOST.totalVcpuCores, CAST(CLOUD_HOST.allocatedVcpuCores AS FLOAT) / CLOUD_HOST.totalVcpuCores AS allocation_rate FROM CLOUD_HOST INNER JOIN M_ClusterContainsPhyHost ON CLOUD_HOST.id = M_ClusterContainsPhyHost.target_Instance_Id INNER JOIN CLOUD_CLUSTER ON M_ClusterContainsPhyHost.source_Instance_Id = CLOUD_CLUSTER.id",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_068",
    "name": "tpl_068_CMDB-102",
    "description": "资产状态为报废的设备有多少台，分别属于哪些类别",
    "resources": [
      "S_Device"
    ],
    "examples": [
      "资产状态为报废的设备有多少台，分别属于哪些类别"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_Device?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "assetStatus",
              "value": "{{assetStatus}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT class_Name, COUNT(*) AS count FROM SYS_Device GROUP BY class_Name",
    "default_params": {
      "assetStatus": "running"
    }
  },
  {
    "id": "rb_069",
    "name": "tpl_069_CMDB-104",
    "description": "查询X86服务器的基本信息",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询X86服务器的基本信息"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT SYS_X86Server.hostName AS name, SYS_X86Server.hostIpAddress AS ip_address, SYS_X86Server.cpuArch AS cpu_arch, SYS_X86Server.cpuCores AS cpu_cores FROM SYS_X86Server"
  },
  {
    "id": "rb_070",
    "name": "tpl_070_CMDB-105",
    "description": "查询区域region_guian4下交换机数量和路由器数量",
    "resources": [
      "S_Switch",
      "S_Router"
    ],
    "examples": [
      "查询区域region_guian4下交换机数量和路由器数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/S_Switch?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/S_Router?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT 'switch' AS device_type, COUNT(*) AS total FROM SYS_Switch UNION ALL SELECT 'router' AS device_type, COUNT(*) AS total FROM SYS_Router",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_071",
    "name": "tpl_071_CMDB-106",
    "description": "查询区域region_guian4下X86服务器列表",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询区域region_guian4下X86服务器列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT x.hostName AS name, x.hostIpAddress AS ip_address, x.hostType AS type FROM (SELECT *, NULL AS hostName, NULL AS hostIpAddress, NULL AS hostType, NULL AS _empty FROM SYS_X86Server) AS x WHERE x._empty IS NULL"
  },
  {
    "id": "rb_072",
    "name": "tpl_072_CMDB-107",
    "description": "查询区域region_guian4下各区域的物理服务器数量",
    "resources": [
      "S_X86Server"
    ],
    "examples": [
      "查询区域region_guian4下各区域的物理服务器数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_X86Server?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT logicalRegionName, COUNT(*) AS count FROM SYS_X86Server GROUP BY logicalRegionName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_073",
    "name": "tpl_073_CMDB-108",
    "description": "查询区域region_guian4下物理设备按类型分布（服务器/交换机/存储设备）",
    "resources": [
      "S_Device"
    ],
    "examples": [
      "查询区域region_guian4下物理设备按类型分布（服务器/交换机/存储设备）"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_Device?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT class_Name, COUNT(*) AS count FROM SYS_Device GROUP BY class_Name",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_074",
    "name": "tpl_074_CMDB-110",
    "description": "查询区域region_guian4下各租户的ECS虚拟机数量",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下各租户的ECS虚拟机数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT tenantName, COUNT(*) AS count FROM CLOUD_VM_NOVA GROUP BY tenantName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_075",
    "name": "tpl_075_CMDB-112",
    "description": "查询租户AdvanceService_System_VDC的ECS虚拟机列表",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC的ECS虚拟机列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "vdcName",
              "value": "{{vdcName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, status, nativeId FROM CLOUD_VM_NOVA",
    "default_params": {
      "vdcName": "AdvanceService_System_VDC"
    }
  },
  {
    "id": "rb_076",
    "name": "tpl_076_CMDB-113",
    "description": "查询云服务ApiCom的微服务实例部署节点信息",
    "resources": [
      "S_CloudService"
    ],
    "examples": [
      "查询云服务ApiCom的微服务实例部署节点信息"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_CloudService?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "indexName",
              "value": "{{indexName}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT SYS_DeployNode.name AS node_name, SYS_DeployNode.id AS node_id, SYS_DeployNode.hostName AS host_name, SYS_DeployNode.mgmtIp AS mgmt_ip FROM SYS_CloudService INNER JOIN SYS_Service ON SYS_CloudService.id = SYS_Service.cloudServiceId INNER JOIN SYS_DeployComponent ON SYS_Service.id = SYS_DeployComponent.serviceId INNER JOIN SYS_DeployInstance ON SYS_DeployComponent.id = SYS_DeployInstance.deployComponentId INNER JOIN SYS_DeployNode ON SYS_DeployInstance.deployNodeId = SYS_DeployNode.id",
    "default_params": {
      "indexName": "ApiCom"
    }
  },
  {
    "id": "rb_077",
    "name": "tpl_077_CMDB-114",
    "description": "云服务ApiCom的微服务部署在哪些节点上，节点类型是虚拟机还是物理机",
    "resources": [
      "S_CloudService"
    ],
    "examples": [
      "云服务ApiCom的微服务部署在哪些节点上，节点类型是虚拟机还是物理机"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_CloudService?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "indexName",
              "value": "{{indexName}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT SYS_DeployNode.name AS node_name, SYS_DeployNode.hostClass AS host_class FROM SYS_CloudService INNER JOIN SYS_Service ON SYS_CloudService.id = SYS_Service.cloudServiceId INNER JOIN SYS_DeployComponent ON SYS_Service.id = SYS_DeployComponent.serviceId INNER JOIN SYS_DeployInstance ON SYS_DeployComponent.id = SYS_DeployInstance.deployComponentId INNER JOIN SYS_DeployNode ON SYS_DeployInstance.deployNodeId = SYS_DeployNode.id",
    "default_params": {
      "indexName": "ApiCom"
    }
  },
  {
    "id": "rb_078",
    "name": "tpl_078_CMDB-115",
    "description": "查询区域region_guian4下各云服务的微服务实例数量",
    "resources": [
      "S_CloudService"
    ],
    "examples": [
      "查询区域region_guian4下各云服务的微服务实例数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_CloudService?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT SYS_CloudService.indexName AS cloud_service_name, COUNT(*) AS instance_count FROM SYS_CloudService INNER JOIN SYS_Service ON SYS_CloudService.id = SYS_Service.cloudServiceId INNER JOIN SYS_DeployComponent ON SYS_Service.id = SYS_DeployComponent.serviceId INNER JOIN SYS_DeployInstance ON SYS_DeployComponent.id = SYS_DeployInstance.deployComponentId GROUP BY SYS_CloudService.indexName"
  },
  {
    "id": "rb_079",
    "name": "tpl_079_CMDB-116",
    "description": "查询区域region_guian4下部署节点按hostClass(VM/PM)分布",
    "resources": [
      "S_DeployNode"
    ],
    "examples": [
      "查询区域region_guian4下部署节点按hostClass(VM/PM)分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_DeployNode?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT hostClass, COUNT(*) AS count FROM SYS_DeployNode GROUP BY hostClass"
  },
  {
    "id": "rb_080",
    "name": "tpl_080_CMDB-118",
    "description": "查询部署节点APIGWLB-01_roma-guian-4关联的管理虚拟机信息",
    "resources": [
      "S_DeployNode"
    ],
    "examples": [
      "查询部署节点APIGWLB-01_roma-guian-4关联的管理虚拟机信息"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/S_DeployNode?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.id AS vm_id, CLOUD_VM_NOVA.privateIps AS private_ips, CLOUD_VM_NOVA.status AS status FROM SYS_DeployNode INNER JOIN CLOUD_VM_NOVA ON SYS_DeployNode.vmId = CLOUD_VM_NOVA.id",
    "default_params": {
      "name": "APIGWLB-01_roma-guian-4"
    }
  },
  {
    "id": "rb_081",
    "name": "tpl_081_CMDB-121",
    "description": "帮我统计所有云硬盘按状态和类型的分布情况",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "帮我统计所有云硬盘按状态和类型的分布情况"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT CLOUD_VOLUME.status AS status, 'N/A' AS type_name, COUNT(*) AS count FROM CLOUD_VOLUME GROUP BY CLOUD_VOLUME.status, 'N/A'"
  },
  {
    "id": "rb_082",
    "name": "tpl_082_CMDB-122",
    "description": "云硬盘都有哪些状态，各有多少，容量最大的是哪个",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "云硬盘都有哪些状态，各有多少，容量最大的是哪个"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT status, COUNT(*) AS count FROM CLOUD_VOLUME GROUP BY status ORDER BY count DESC"
  },
  {
    "id": "rb_083",
    "name": "tpl_083_CMDB-123",
    "description": "当前处于异常状态的云硬盘有多少块，分别是什么类型",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "当前处于异常状态的云硬盘有多少块，分别是什么类型"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "status",
              "value": "{{status}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS total FROM CLOUD_VOLUME",
    "default_params": {
      "status": "error"
    }
  },
  {
    "id": "rb_084",
    "name": "tpl_084_CMDB-127",
    "description": "可启动云硬盘在所有云硬盘中占比多少",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "可启动云硬盘在所有云硬盘中占比多少"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "bootable",
                "value": "{{bootable}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "bootable",
                "value": "{{bootable}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT 'bootable' AS type, COUNT(*) AS count FROM CLOUD_VOLUME",
    "default_params": {
      "bootable": "True"
    }
  },
  {
    "id": "rb_085",
    "name": "tpl_085_CMDB-128",
    "description": "查询区域region_guian4可用区az0.dc0中可启动云硬盘列表",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4可用区az0.dc0中可启动云硬盘列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "bootable",
              "value": "{{bootable}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, size, status, bootable FROM CLOUD_VOLUME",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "azoneName": "az_guian4",
      "bootable": "True"
    }
  },
  {
    "id": "rb_086",
    "name": "tpl_086_CMDB-130",
    "description": "查询区域region_guian4下各VDC的云硬盘数量和总容量",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的云硬盘数量和总容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS count, SUM(size) AS total_size FROM CLOUD_VOLUME GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_087",
    "name": "tpl_087_CMDB-132",
    "description": "查询区域region_guian4下各VDC的云硬盘数量和总容量",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的云硬盘数量和总容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS count, SUM(size) AS total_size FROM CLOUD_VOLUME GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_088",
    "name": "tpl_088_CMDB-133",
    "description": "查询VDCAdvanceService_Manage_VDC在区域region_guian4中的云硬盘列表及容量",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "查询VDCAdvanceService_Manage_VDC在区域region_guian4中的云硬盘列表及容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "vdcName",
              "value": "{{vdcName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VOLUME.name AS name, CLOUD_VOLUME.size AS size, CLOUD_VOLUME.status AS status, 'N/A' AS type_name FROM CLOUD_VOLUME",
    "default_params": {
      "vdcName": "AdvanceService_Manage_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_089",
    "name": "tpl_089_CMDB-134",
    "description": "帮我查询ECS实例cse-engine-cluster-roma-guian-4-3-master-1挂载的所有云硬盘",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "帮我查询ECS实例cse-engine-cluster-roma-guian-4-3-master-1挂载的所有云硬盘"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VOLUME.name AS volume_name, CLOUD_VOLUME.size AS size_gb, CLOUD_VOLUME.bootable AS bootable, CLOUD_VOLUME.status AS status FROM CLOUD_VM_NOVA INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VM_NOVA.id = R_VOLUME_MOUNTON_VM.vmId INNER JOIN CLOUD_VOLUME ON R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_090",
    "name": "tpl_090_CMDB-135",
    "description": "ECScse-engine-cluster-roma-guian-4-3-master-1挂载的云硬盘中哪些是系统盘，哪",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "ECScse-engine-cluster-roma-guian-4-3-master-1挂载的云硬盘中哪些是系统盘，哪些是数据盘"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VOLUME.bootable AS bootable, CLOUD_VOLUME.name AS volume_name, CLOUD_VOLUME.size AS size FROM CLOUD_VM_NOVA INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VM_NOVA.id = R_VOLUME_MOUNTON_VM.vmId INNER JOIN CLOUD_VOLUME ON R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id ORDER BY CLOUD_VOLUME.bootable",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_091",
    "name": "tpl_091_CMDB-136",
    "description": "帮我查询云硬盘functiongraph-manager-9oslr-volume-0000挂载到了哪台ECS实例",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "帮我查询云硬盘functiongraph-manager-9oslr-volume-0000挂载到了哪台ECS实例"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VOLUME.name AS volume_name, CLOUD_VOLUME.size AS size, CLOUD_VOLUME.status AS status, CLOUD_VM_NOVA.name AS vm_name FROM CLOUD_VOLUME INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VOLUME.id = R_VOLUME_MOUNTON_VM.volumeId INNER JOIN CLOUD_VM_NOVA ON R_VOLUME_MOUNTON_VM.vmId = CLOUD_VM_NOVA.id",
    "default_params": {
      "name": "functiongraph-manager-9oslr-volume-0000"
    }
  },
  {
    "id": "rb_092",
    "name": "tpl_092_CMDB-137",
    "description": "云硬盘functiongraph-manager-9oslr-volume-0000当前是否已挂载",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "云硬盘functiongraph-manager-9oslr-volume-0000当前是否已挂载"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, status FROM CLOUD_VOLUME",
    "default_params": {
      "name": "functiongraph-manager-9oslr-volume-0000"
    }
  },
  {
    "id": "rb_093",
    "name": "tpl_093_CMDB-139",
    "description": "查询区域region_guian4下各VDC的GaussDB实例关联的后端存储池名称",
    "resources": [
      "GAUSSDB_INSTANCE",
      "STORAGE_POOL"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的GaussDB实例关联的后端存储池名称"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{storagePoolId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_GAUSSDB_INSTANCE.vdcName AS vdc_name, CLOUD_GAUSSDB_INSTANCE.name AS instance_name, 'N/A' AS pool_name FROM CLOUD_GAUSSDB_INSTANCE GROUP BY CLOUD_GAUSSDB_INSTANCE.vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_094",
    "name": "tpl_094_CMDB-140",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1挂载的云硬盘中容量最大的一",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1挂载的云硬盘中容量最大的一个，返回名称和容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VOLUME.name AS volume_name, CLOUD_VOLUME.size AS size FROM CLOUD_VM_NOVA INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VM_NOVA.id = R_VOLUME_MOUNTON_VM.vmId INNER JOIN CLOUD_VOLUME ON R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id ORDER BY CLOUD_VOLUME.size DESC LIMIT 1",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_095",
    "name": "tpl_095_CMDB-141",
    "description": "帮我查询存储池cinder-kvm003@bussiness_storage02#0的容量使用情况",
    "resources": [
      "STORAGE_POOL"
    ],
    "examples": [
      "帮我查询存储池cinder-kvm003@bussiness_storage02#0的容量使用情况"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, totalCapacityGB, freeCapacityGB, provisionedCapacityGB, (totalCapacityGB - freeCapacityGB) AS used_capacity, ROUND((totalCapacityGB - freeCapacityGB) * 100.0 / totalCapacityGB, 2) AS usage_rate, ROUND(provisionedCapacityGB * 100.0 / totalCapacityGB, 2) AS over_subscription_ratio FROM CLOUD_STORAGE_POOL",
    "default_params": {
      "name": "cinder-kvm003@bussiness_storage02#0"
    }
  },
  {
    "id": "rb_096",
    "name": "tpl_096_CMDB-143",
    "description": "查询区域region_guian4下各可用区的存储池容量使用情况",
    "resources": [
      "STORAGE_POOL"
    ],
    "examples": [
      "查询区域region_guian4下各可用区的存储池容量使用情况"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT azoneName, SUM(totalCapacityGB) AS total_capacity, SUM(freeCapacityGB) AS free_capacity, (SUM(totalCapacityGB) - SUM(freeCapacityGB)) AS used_capacity, ROUND((SUM(totalCapacityGB) - SUM(freeCapacityGB)) * 100.0 / SUM(totalCapacityGB), 2) AS usage_rate FROM CLOUD_STORAGE_POOL GROUP BY azoneName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_097",
    "name": "tpl_097_CMDB-144",
    "description": "查询可用区az0.dc0下各存储池的已用容量和使用率，按使用率降序",
    "resources": [
      "STORAGE_POOL"
    ],
    "examples": [
      "查询可用区az0.dc0下各存储池的已用容量和使用率，按使用率降序"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, totalCapacityGB, freeCapacityGB, (totalCapacityGB - freeCapacityGB) AS used_capacity, ROUND((totalCapacityGB - freeCapacityGB) * 100.0 / totalCapacityGB, 2) AS usage_rate FROM CLOUD_STORAGE_POOL ORDER BY usage_rate DESC",
    "default_params": {
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_098",
    "name": "tpl_098_CMDB-147",
    "description": "查询区域region_guian4下各可用区的存储池名称、磁盘类型、物理容量总量、已用量、可用量和超配比",
    "resources": [
      "STORAGE_POOL"
    ],
    "examples": [
      "查询区域region_guian4下各可用区的存储池名称、磁盘类型、物理容量总量、已用量、可用量和超配比"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT azoneName, storageProtocol, SUM(totalCapacityGB) AS total_capacity, SUM(totalCapacityGB - freeCapacityGB) AS used_capacity, SUM(freeCapacityGB) AS free_capacity, ROUND(SUM(provisionedCapacityGB) * 100.0 / SUM(totalCapacityGB), 2) AS over_subscription_ratio FROM CLOUD_STORAGE_POOL GROUP BY azoneName, storageProtocol",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_099",
    "name": "tpl_099_CMDB-148",
    "description": "查询区域region_guian4下OBS桶列表",
    "resources": [
      "OBS_BUCKET"
    ],
    "examples": [
      "查询区域region_guian4下OBS桶列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/OBS_BUCKET?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, bucketName, managedStatus FROM CLOUD_OBS_BUCKET",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_100",
    "name": "tpl_100_CMDB-149",
    "description": "查询租户AdvanceService_System_VDC的OBS桶数量和总容量",
    "resources": [
      "OBS_BUCKET"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC的OBS桶数量和总容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/OBS_BUCKET?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "tenantName",
              "value": "{{tenantName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS total_count FROM CLOUD_OBS_BUCKET",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC"
    }
  },
  {
    "id": "rb_101",
    "name": "tpl_101_CMDB-150",
    "description": "查询区域region_guian4下各租户的OBS桶数量",
    "resources": [
      "OBS_BUCKET"
    ],
    "examples": [
      "查询区域region_guian4下各租户的OBS桶数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/OBS_BUCKET?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT tenantName, COUNT(*) AS count FROM CLOUD_OBS_BUCKET GROUP BY tenantName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_102",
    "name": "tpl_102_CMDB-151",
    "description": "查询区域region_guian4下各VDC的云硬盘平均容量和最大容量",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的云硬盘平均容量和最大容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, AVG(size) AS avg_size, MAX(size) AS max_size FROM CLOUD_VOLUME GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_103",
    "name": "tpl_103_CMDB-152",
    "description": "查询区域region_guian4下挂载云硬盘数量最多的前5台ECS，返回ECS名和挂载数量",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下挂载云硬盘数量最多的前5台ECS，返回ECS名和挂载数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, COUNT(*) AS volume_count FROM CLOUD_VM_NOVA INNER JOIN R_VOLUME_MOUNTON_VM ON CLOUD_VM_NOVA.id = R_VOLUME_MOUNTON_VM.vmId INNER JOIN CLOUD_VOLUME ON R_VOLUME_MOUNTON_VM.volumeId = CLOUD_VOLUME.id GROUP BY CLOUD_VM_NOVA.name ORDER BY volume_count DESC LIMIT 5",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_104",
    "name": "tpl_104_CMDB-153",
    "description": "查询区域region_guian4下各厂商存储池的总容量和可用容量",
    "resources": [
      "STORAGE_POOL"
    ],
    "examples": [
      "查询区域region_guian4下各厂商存储池的总容量和可用容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vendorName, SUM(totalCapacityGB) AS total_capacity, SUM(freeCapacityGB) AS free_capacity FROM CLOUD_STORAGE_POOL GROUP BY vendorName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_105",
    "name": "tpl_105_CMDB-154",
    "description": "查询区域region_guian4下GaussDB实例按规格分布",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询区域region_guian4下GaussDB实例按规格分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT flavorCode, COUNT(*) AS count FROM CLOUD_GAUSSDB_INSTANCE GROUP BY flavorCode",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_106",
    "name": "tpl_106_CMDB-156",
    "description": "查询区域region_guian4下各VDC的GaussDB实例数量和总存储容量",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的GaussDB实例数量和总存储容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS instance_count, SUM(dataVolumeSizeInGBs) AS total_storage FROM CLOUD_GAUSSDB_INSTANCE GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_107",
    "name": "tpl_107_CMDB-158",
    "description": "查询GaussDB实例gauss-dbmind-4463使用的ECS实例",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询GaussDB实例gauss-dbmind-4463使用的ECS实例"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_GAUSSDB_INSTANCE.name AS instance_name, CLOUD_GAUSSDB_NODE.name AS node_name, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS vm_ip FROM CLOUD_GAUSSDB_INSTANCE INNER JOIN CLOUD_GAUSSDB_NODE ON CLOUD_GAUSSDB_INSTANCE.id = CLOUD_GAUSSDB_NODE.ref_instanceId INNER JOIN CLOUD_VM_NOVA ON CLOUD_GAUSSDB_NODE.ref_vmbmsId = CLOUD_VM_NOVA.id",
    "default_params": {
      "name": "gauss-dbmind-4463"
    }
  },
  {
    "id": "rb_108",
    "name": "tpl_108_CMDB-161",
    "description": "一共有多少VPC，VPC下有哪些子网，子网下有哪些虚拟机",
    "resources": [
      "ROUTER"
    ],
    "examples": [
      "一共有多少VPC，VPC下有哪些子网，子网下有哪些虚拟机"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT COUNT(*) AS total FROM CLOUD_ROUTER"
  },
  {
    "id": "rb_109",
    "name": "tpl_109_CMDB-163",
    "description": "查询区域region_guian4下各VDC的VPC数量",
    "resources": [
      "ROUTER"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的VPC数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS count FROM CLOUD_ROUTER GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_110",
    "name": "tpl_110_CMDB-165",
    "description": "帮我查询所有共享网络的清单",
    "resources": [
      "NETWORK"
    ],
    "examples": [
      "帮我查询所有共享网络的清单"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/NETWORK?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "shared",
              "value": "{{shared}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, providerNetworkType, providerPhysicalNetworkSegId FROM CLOUD_NETWORK",
    "default_params": {
      "shared": "True"
    }
  },
  {
    "id": "rb_111",
    "name": "tpl_111_CMDB-166",
    "description": "共享网络中providerNetworkType为vlan的有多少个",
    "resources": [
      "NETWORK"
    ],
    "examples": [
      "共享网络中providerNetworkType为vlan的有多少个"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/NETWORK?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "shared",
              "value": "{{shared}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "providerNetworkType",
              "value": "{{providerNetworkType}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS total FROM CLOUD_NETWORK",
    "default_params": {
      "shared": "True",
      "providerNetworkType": "vlan"
    }
  },
  {
    "id": "rb_112",
    "name": "tpl_112_CMDB-167",
    "description": "查询区域region_guian4下共享网络数量",
    "resources": [
      "NETWORK"
    ],
    "examples": [
      "查询区域region_guian4下共享网络数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/NETWORK?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "shared",
              "value": "{{shared}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS count FROM CLOUD_NETWORK",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "shared": "True"
    }
  },
  {
    "id": "rb_113",
    "name": "tpl_113_CMDB-169",
    "description": "查询区域region_guian4下各VDC的弹性IP数量",
    "resources": [
      "FLOATING_IPS"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的弹性IP数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS count FROM CLOUD_FLOATING_IPS GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_114",
    "name": "tpl_114_CMDB-170",
    "description": "查询区域region_guian4下所有未绑定EIP的列表",
    "resources": [
      "FLOATING_IPS"
    ],
    "examples": [
      "查询区域region_guian4下所有未绑定EIP的列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "status",
              "value": "{{status}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT floatingIpAddress AS eip_address, status FROM CLOUD_FLOATING_IPS",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "status": "DOWN"
    }
  },
  {
    "id": "rb_115",
    "name": "tpl_115_CMDB-173",
    "description": "查询区域region_guian4下ELB列表及监听器",
    "resources": [
      "ELB"
    ],
    "examples": [
      "查询区域region_guian4下ELB列表及监听器"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_ELB.name AS elb_name, CLOUD_ELB.id AS elb_id, CLOUD_LISTENER.name AS listener_name, CLOUD_LISTENER.protocol AS listener_protocol, CLOUD_LISTENER.port AS listener_port FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_116",
    "name": "tpl_116_CMDB-174",
    "description": "查询ELBcloudpipeline_backend_elb的监听器列表",
    "resources": [
      "ELB"
    ],
    "examples": [
      "查询ELBcloudpipeline_backend_elb的监听器列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_ELB.name AS elb_name, CLOUD_LISTENER.name AS listener_name, CLOUD_LISTENER.protocol AS protocol, CLOUD_LISTENER.port AS port FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId",
    "default_params": {
      "name": "cloudpipeline_backend_elb"
    }
  },
  {
    "id": "rb_117",
    "name": "tpl_117_CMDB-175",
    "description": "查询ELBcloudpipeline_backend_elb的监听器列表和监听端口",
    "resources": [
      "ELB"
    ],
    "examples": [
      "查询ELBcloudpipeline_backend_elb的监听器列表和监听端口"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_LISTENER.name AS listener_name, CLOUD_LISTENER.protocol AS protocol, CLOUD_LISTENER.port AS port FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId",
    "default_params": {
      "name": "cloudpipeline_backend_elb"
    }
  },
  {
    "id": "rb_118",
    "name": "tpl_118_CMDB-176",
    "description": "查询ELBcloudpipeline_backend_elb关联的弹性IP",
    "resources": [
      "ELB"
    ],
    "examples": [
      "查询ELBcloudpipeline_backend_elb关联的弹性IP"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_ELB.name AS elb_name, CLOUD_FLOATING_IPS.floatingIpAddress AS floating_ip FROM CLOUD_ELB INNER JOIN CLOUD_FLOATING_IPS ON CLOUD_ELB.ip = CLOUD_FLOATING_IPS.fixedIpAddress",
    "default_params": {
      "name": "cloudpipeline_backend_elb"
    }
  },
  {
    "id": "rb_119",
    "name": "tpl_119_CMDB-179",
    "description": "查询区域region_guian4下ELB按监听协议分布",
    "resources": [
      "ELB"
    ],
    "examples": [
      "查询区域region_guian4下ELB按监听协议分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_LISTENER.protocol AS protocol, COUNT(*) AS count FROM CLOUD_ELB INNER JOIN CLOUD_LISTENER ON CLOUD_ELB.id = CLOUD_LISTENER.elbId GROUP BY CLOUD_LISTENER.protocol",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_120",
    "name": "tpl_120_CMDB-180",
    "description": "查询区域region_guian4下ELB数量",
    "resources": [
      "ELB"
    ],
    "examples": [
      "查询区域region_guian4下ELB数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS count FROM CLOUD_ELB",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_121",
    "name": "tpl_121_CMDB-181",
    "description": "帮我查询ECS实例cse-engine-cluster-roma-guian-4-3-master-1的网卡端口及关联的",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "帮我查询ECS实例cse-engine-cluster-roma-guian-4-3-master-1的网卡端口及关联的子网信息"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_PORT.name AS port_name, CLOUD_PORT.mac AS mac, CLOUD_PORT.ipAddresses AS ip, CLOUD_SUBNET.cidr AS subnet_cidr, CLOUD_SUBNET.gatewayIp AS gateway FROM CLOUD_VM_NOVA INNER JOIN CLOUD_PORT ON CLOUD_VM_NOVA.resId = CLOUD_PORT.devId INNER JOIN R_PORT_IN_SUBNET ON CLOUD_PORT.id = R_PORT_IN_SUBNET.portId INNER JOIN CLOUD_SUBNET ON R_PORT_IN_SUBNET.subnetId = CLOUD_SUBNET.id",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_122",
    "name": "tpl_122_CMDB-182",
    "description": "ECScse-engine-cluster-roma-guian-4-3-master-1有几块网卡，分别关联的子网CI",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "ECScse-engine-cluster-roma-guian-4-3-master-1有几块网卡，分别关联的子网CIDR是什么"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS port_count FROM CLOUD_VM_NOVA INNER JOIN CLOUD_PORT ON CLOUD_VM_NOVA.resId = CLOUD_PORT.devId",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_123",
    "name": "tpl_123_CMDB-183",
    "description": "查询ECS rds-a357-1的网卡列表",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECS rds-a357-1的网卡列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_PORT.name AS port_name, CLOUD_PORT.mac AS mac_address, CLOUD_PORT.status AS port_status FROM CLOUD_VM_NOVA INNER JOIN CLOUD_PORT ON CLOUD_VM_NOVA.resId = CLOUD_PORT.devId",
    "default_params": {
      "name": "rds-a357-1"
    }
  },
  {
    "id": "rb_124",
    "name": "tpl_124_CMDB-184",
    "description": "查询ECScse-engine-cluster-roma-guian-4-3-master-1的网卡关联的安全组",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询ECScse-engine-cluster-roma-guian-4-3-master-1的网卡关联的安全组"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_SECURITY_GROUP.name AS sg_name FROM CLOUD_VM_NOVA INNER JOIN CLOUD_PORT ON CLOUD_VM_NOVA.resId = CLOUD_PORT.devId INNER JOIN R_PORT_USE_SECURITY_GROUP ON CLOUD_PORT.id = R_PORT_USE_SECURITY_GROUP.portId INNER JOIN CLOUD_SECURITY_GROUP ON R_PORT_USE_SECURITY_GROUP.sgId = CLOUD_SECURITY_GROUP.id",
    "default_params": {
      "name": "cse-engine-cluster-roma-guian-4-3-master-1"
    }
  },
  {
    "id": "rb_125",
    "name": "tpl_125_CMDB-185",
    "description": "查询子网OM_ECMP下有哪些网卡端口",
    "resources": [
      "SUBNET"
    ],
    "examples": [
      "查询子网OM_ECMP下有哪些网卡端口"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_PORT.name AS port_name, CLOUD_PORT.mac AS mac, CLOUD_PORT.ipAddresses AS ip FROM CLOUD_SUBNET INNER JOIN R_PORT_IN_SUBNET ON CLOUD_SUBNET.id = R_PORT_IN_SUBNET.subnetId INNER JOIN CLOUD_PORT ON R_PORT_IN_SUBNET.portId = CLOUD_PORT.id",
    "default_params": {
      "name": "OM_ECMP"
    }
  },
  {
    "id": "rb_126",
    "name": "tpl_126_CMDB-187",
    "description": "安全组default中哪些规则允许了外部访问，关联了多少个端口",
    "resources": [
      "SECURITY_GROUP",
      "SECURITY_GROUP_RULE"
    ],
    "examples": [
      "安全组default中哪些规则允许了外部访问，关联了多少个端口"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP_RULE?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "securityGroupId",
                "value": "{{id from step 1}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "direction",
                "value": "{{direction}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS port_count FROM CLOUD_SECURITY_GROUP INNER JOIN R_PORT_USE_SECURITY_GROUP ON CLOUD_SECURITY_GROUP.id = R_PORT_USE_SECURITY_GROUP.sgId INNER JOIN CLOUD_PORT ON R_PORT_USE_SECURITY_GROUP.portId = CLOUD_PORT.id",
    "default_params": {
      "name": "default",
      "direction": "ingress"
    }
  },
  {
    "id": "rb_127",
    "name": "tpl_127_CMDB-188",
    "description": "查询安全组default关联的端口列表及端口所属的ECS",
    "resources": [
      "SECURITY_GROUP"
    ],
    "examples": [
      "查询安全组default关联的端口列表及端口所属的ECS"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_PORT.name AS port_name, CLOUD_PORT.id AS port_id, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS vm_ip FROM CLOUD_SECURITY_GROUP INNER JOIN R_PORT_USE_SECURITY_GROUP ON CLOUD_SECURITY_GROUP.id = R_PORT_USE_SECURITY_GROUP.sgId INNER JOIN CLOUD_PORT ON R_PORT_USE_SECURITY_GROUP.portId = CLOUD_PORT.id INNER JOIN CLOUD_VM_NOVA ON CLOUD_PORT.devId = CLOUD_VM_NOVA.resId",
    "default_params": {
      "name": "default"
    }
  },
  {
    "id": "rb_128",
    "name": "tpl_128_CMDB-189",
    "description": "查询所有的安全组列表及规则数量",
    "resources": [
      "ROUTER",
      "SECURITY_GROUP"
    ],
    "examples": [
      "查询所有的安全组列表及规则数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT CLOUD_SECURITY_GROUP.name AS sg_name, CLOUD_SECURITY_GROUP.id AS sg_id, COUNT(CLOUD_SECURITY_GROUP_RULE.id) AS rule_count FROM CLOUD_SECURITY_GROUP INNER JOIN CLOUD_SECURITY_GROUP_RULE ON CLOUD_SECURITY_GROUP.id = CLOUD_SECURITY_GROUP_RULE.securityGroupId GROUP BY CLOUD_SECURITY_GROUP.name, CLOUD_SECURITY_GROUP.id",
    "default_params": {
      "name": "dbs_resource_vpc_c_type"
    }
  },
  {
    "id": "rb_129",
    "name": "tpl_129_CMDB-190",
    "description": "查询区域region_guian4下各VDC的安全组数量和规则总数",
    "resources": [
      "SECURITY_GROUP"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的安全组数量和规则总数"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT vdcName, COUNT(*) AS sg_count FROM CLOUD_SECURITY_GROUP GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_130",
    "name": "tpl_130_CMDB-192",
    "description": "VPCdbs_resource_vpc_c_type下有多少个子网和弹性IP",
    "resources": [
      "ROUTER",
      "FLOATING_IPS"
    ],
    "examples": [
      "VPCdbs_resource_vpc_c_type下有多少个子网和弹性IP"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "routerId",
                "value": "{{id from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS subnet_count FROM CLOUD_ROUTER INNER JOIN CLOUD_PORT ON CLOUD_ROUTER.nativeId = CLOUD_PORT.devNativeId INNER JOIN R_PORT_IN_SUBNET ON CLOUD_PORT.id = R_PORT_IN_SUBNET.portId INNER JOIN CLOUD_SUBNET ON R_PORT_IN_SUBNET.subnetId = CLOUD_SUBNET.id",
    "default_params": {
      "name": "dbs_resource_vpc_c_type"
    }
  },
  {
    "id": "rb_131",
    "name": "tpl_131_CMDB-194",
    "description": "查询VDCAdvanceService_Manage_VDC在区域region_guian4中的VPC名称、子网CIDR",
    "resources": [
      "ROUTER",
      "SUBNET",
      "FLOATING_IPS"
    ],
    "examples": [
      "查询VDCAdvanceService_Manage_VDC在区域region_guian4中的VPC名称、子网CIDR和弹性IP数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT name AS subnet_name, cidr AS subnet_cidr FROM CLOUD_SUBNET",
    "default_params": {
      "vdcName": "AdvanceService_Manage_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_132",
    "name": "tpl_132_CMDB-196",
    "description": "查询区域region_guian4下各VDC的VPC名称和子网数量",
    "resources": [
      "ROUTER"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的VPC名称和子网数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT vdcName, name AS vpc_name FROM CLOUD_ROUTER",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_133",
    "name": "tpl_133_CMDB-197",
    "description": "查询区域region_guian4下各租户的弹性IP绑定状态",
    "resources": [
      "FLOATING_IPS"
    ],
    "examples": [
      "查询区域region_guian4下各租户的弹性IP绑定状态"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT tenantName, status, COUNT(*) AS count FROM CLOUD_FLOATING_IPS GROUP BY tenantName, status",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_134",
    "name": "tpl_134_CMDB-199",
    "description": "查询VPCdbs_resource_vpc_c_type下的子网列表及每个子网的IP使用率",
    "resources": [
      "ROUTER"
    ],
    "examples": [
      "查询VPCdbs_resource_vpc_c_type下的子网列表及每个子网的IP使用率"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_SUBNET.name AS subnet_name, CLOUD_SUBNET.cidr AS subnet_cidr, COUNT(CLOUD_PORT.id) AS used_ip_count FROM CLOUD_ROUTER INNER JOIN CLOUD_PORT ON CLOUD_ROUTER.nativeId = CLOUD_PORT.devNativeId INNER JOIN R_PORT_IN_SUBNET ON CLOUD_PORT.id = R_PORT_IN_SUBNET.portId INNER JOIN CLOUD_SUBNET ON R_PORT_IN_SUBNET.subnetId = CLOUD_SUBNET.id GROUP BY CLOUD_SUBNET.name, CLOUD_SUBNET.cidr",
    "default_params": {
      "name": "dbs_resource_vpc_c_type"
    }
  },
  {
    "id": "rb_135",
    "name": "tpl_135_CMDB-200",
    "description": "查询区域region_guian4下各VDC的VPC、子网、弹性IP和安全组数量汇总",
    "resources": [
      "ROUTER",
      "SUBNET",
      "FLOATING_IPS",
      "SECURITY_GROUP"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的VPC、子网、弹性IP和安全组数量汇总"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT vdcName, COUNT(*) AS sg_count FROM CLOUD_SECURITY_GROUP GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_136",
    "name": "tpl_136_CMDB-202",
    "description": "子网OM_ECMP的IP使用率是多少，还剩多少可用IP",
    "resources": [
      "SUBNET"
    ],
    "examples": [
      "子网OM_ECMP的IP使用率是多少，还剩多少可用IP"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT name AS subnet_name, cidr AS subnet_cidr FROM CLOUD_SUBNET",
    "default_params": {
      "name": "OM_ECMP"
    }
  },
  {
    "id": "rb_137",
    "name": "tpl_137_CMDB-204",
    "description": "查询区域region_guian4下子网数量和CIDR范围",
    "resources": [
      "SUBNET"
    ],
    "examples": [
      "查询区域region_guian4下子网数量和CIDR范围"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT cidr AS subnet_cidr FROM CLOUD_SUBNET",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_138",
    "name": "tpl_138_CMDB-206",
    "description": "查询区域region_guian4下子网IP总量和已分配量",
    "resources": [
      "SUBNET"
    ],
    "examples": [
      "查询区域region_guian4下子网IP总量和已分配量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT name AS subnet_name, cidr AS subnet_cidr FROM CLOUD_SUBNET",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_139",
    "name": "tpl_139_CMDB-207",
    "description": "查询区域region_guian4下网络节点列表",
    "resources": [
      "NET_NODE"
    ],
    "examples": [
      "查询区域region_guian4下网络节点列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/NET_NODE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_NET_NODE.name AS node_name, CLOUD_NET_NODE.ipAddress AS ip_address, CLOUD_NET_NODE.managedStatus AS status, CLOUD_NET_NODE.serviceType AS service_type FROM CLOUD_NET_NODE",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_140",
    "name": "tpl_140_CMDB-208",
    "description": "查询虚拟防火墙demo-env-ecs的基本信息",
    "resources": [
      "VFW"
    ],
    "examples": [
      "查询虚拟防火墙demo-env-ecs的基本信息"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VFW?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, status FROM CLOUD_VFW",
    "default_params": {
      "name": "demo-env-ecs"
    }
  },
  {
    "id": "rb_141",
    "name": "tpl_141_CMDB-210",
    "description": "查询区域region_guian4下各VDC的虚拟防火墙数量",
    "resources": [
      "VFW"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的虚拟防火墙数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VFW?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS count FROM CLOUD_VFW GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_142",
    "name": "tpl_142_CMDB-212",
    "description": "查询区域region_guian4下GaussDB实例清单及数据库版本",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询区域region_guian4下GaussDB实例清单及数据库版本"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, engineName, engineVersion, haMode, flavorCode FROM CLOUD_GAUSSDB_INSTANCE",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_143",
    "name": "tpl_143_CMDB-214",
    "description": "查询区域region_guian4下各引擎版本的GaussDB实例数量",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询区域region_guian4下各引擎版本的GaussDB实例数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT engineVersion, COUNT(*) AS count FROM CLOUD_GAUSSDB_INSTANCE GROUP BY engineVersion",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_144",
    "name": "tpl_144_CMDB-215",
    "description": "查询区域region_guian4下GaussDB按haMode分布",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询区域region_guian4下GaussDB按haMode分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT haMode, COUNT(*) AS count FROM CLOUD_GAUSSDB_INSTANCE GROUP BY haMode",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_145",
    "name": "tpl_145_CMDB-217",
    "description": "查询GaussDB实例gauss-dbmind-4463的引擎版本、高可用模式和规格",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询GaussDB实例gauss-dbmind-4463的引擎版本、高可用模式和规格"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT engineVersion, haMode, flavorCode FROM CLOUD_GAUSSDB_INSTANCE",
    "default_params": {
      "name": "gauss-dbmind-4463"
    }
  },
  {
    "id": "rb_146",
    "name": "tpl_146_CMDB-218",
    "description": "查询区域region_guian4中GaussDB实例的引擎版本和数据VIP",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询区域region_guian4中GaussDB实例的引擎版本和数据VIP"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, engineVersion, dataVip FROM CLOUD_GAUSSDB_INSTANCE",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_147",
    "name": "tpl_147_CMDB-219",
    "description": "查询GaussDB实例gauss-dbmind-4463的节点数量和各节点名称",
    "resources": [
      "GAUSSDB_INSTANCE",
      "GAUSSDB_NODE"
    ],
    "examples": [
      "查询GaussDB实例gauss-dbmind-4463的节点数量和各节点名称"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_NODE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "ref_instanceId",
                "value": "{{id from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_GAUSSDB_NODE.name AS node_name, COUNT(*) AS node_count FROM CLOUD_GAUSSDB_INSTANCE INNER JOIN CLOUD_GAUSSDB_NODE ON CLOUD_GAUSSDB_INSTANCE.id = CLOUD_GAUSSDB_NODE.ref_instanceId GROUP BY CLOUD_GAUSSDB_INSTANCE.name",
    "default_params": {
      "name": "gauss-dbmind-4463"
    }
  },
  {
    "id": "rb_148",
    "name": "tpl_148_CMDB-220",
    "description": "查询GaussDB实例gauss-dbmind-4463的高可用模式和数据VIP",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询GaussDB实例gauss-dbmind-4463的高可用模式和数据VIP"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT haMode, dataVip FROM CLOUD_GAUSSDB_INSTANCE",
    "default_params": {
      "name": "gauss-dbmind-4463"
    }
  },
  {
    "id": "rb_149",
    "name": "tpl_149_CMDB-221",
    "description": "查询业务地址为690b8fb9的GaussDB实例名、主机名和所属租户",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询业务地址为690b8fb9的GaussDB实例名、主机名和所属租户"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "dataVip",
              "value": "{{dataVip}}",
              "operator": "contain"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_GAUSSDB_INSTANCE.name AS instance_name, CLOUD_GAUSSDB_INSTANCE.vdcName AS tenant_name, CLOUD_HOST.name AS host_name FROM CLOUD_GAUSSDB_INSTANCE INNER JOIN CLOUD_GAUSSDB_NODE ON CLOUD_GAUSSDB_INSTANCE.id = CLOUD_GAUSSDB_NODE.ref_instanceId INNER JOIN CLOUD_VM_NOVA ON CLOUD_GAUSSDB_NODE.ref_vmbmsId = CLOUD_VM_NOVA.id INNER JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id",
    "default_params": {
      "dataVip": "690b8fb9"
    }
  },
  {
    "id": "rb_150",
    "name": "tpl_150_CMDB-223",
    "description": "查询租户paas-aom下MySQL和PostgreSQL实例分别有多少个",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询租户paas-aom下MySQL和PostgreSQL实例分别有多少个"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "vdcName",
              "value": "{{vdcName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT engineName, COUNT(*) AS count FROM CLOUD_GAUSSDB_INSTANCE GROUP BY engineName",
    "default_params": {
      "vdcName": "paas-aom"
    }
  },
  {
    "id": "rb_151",
    "name": "tpl_151_CMDB-224",
    "description": "查询VDCpaas-mas在区域region_guian4可用区az_guian4中的GaussDB实例列表",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询VDCpaas-mas在区域region_guian4可用区az_guian4中的GaussDB实例列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "vdcName",
              "value": "{{vdcName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, dataVip, engineVersion FROM CLOUD_GAUSSDB_INSTANCE",
    "default_params": {
      "vdcName": "paas-mas",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_152",
    "name": "tpl_152_CMDB-227",
    "description": "查询中间件集群及关联中间件实例",
    "resources": [
      "MIDDLEWARE_CLUSTER"
    ],
    "examples": [
      "查询中间件集群及关联中间件实例"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/MIDDLEWARE_CLUSTER?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT DISTINCT CLOUD_MIDDLEWARE_CLUSTER.name AS cluster_name, CLOUD_MIDDLEWARE.name AS instance_name, CLOUD_MIDDLEWARE.managedStatus AS status FROM CLOUD_MIDDLEWARE_CLUSTER INNER JOIN CLOUD_MIDDLEWARE ON CLOUD_MIDDLEWARE_CLUSTER.id = CLOUD_MIDDLEWARE.parentId"
  },
  {
    "id": "rb_153",
    "name": "tpl_153_CMDB-229",
    "description": "查询中间件集群数量",
    "resources": [
      "MIDDLEWARE_CLUSTER"
    ],
    "examples": [
      "查询中间件集群数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/MIDDLEWARE_CLUSTER?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT COUNT(*) AS total FROM CLOUD_MIDDLEWARE_CLUSTER"
  },
  {
    "id": "rb_154",
    "name": "tpl_154_CMDB-230",
    "description": "查询中间件实例按管理状态分布",
    "resources": [
      "MIDDLEWARE"
    ],
    "examples": [
      "查询中间件实例按管理状态分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/MIDDLEWARE?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT managedStatus, COUNT(*) AS count FROM CLOUD_MIDDLEWARE GROUP BY managedStatus"
  },
  {
    "id": "rb_155",
    "name": "tpl_155_CMDB-231",
    "description": "查询租户paas-aom在区域region_guian4中的RDS实例名、引擎类型、版本和业务IP",
    "resources": [
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询租户paas-aom在区域region_guian4中的RDS实例名、引擎类型、版本和业务IP"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "vdcName",
              "value": "{{vdcName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name, engineName, engineVersion, eip FROM CLOUD_GAUSSDB_INSTANCE",
    "default_params": {
      "vdcName": "paas-aom",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_156",
    "name": "tpl_156_CMDB-234",
    "description": "查询区域region_guian4下GaussDB实例按引擎版本分组数量和中间件按类型分组数量",
    "resources": [
      "GAUSSDB_INSTANCE",
      "MIDDLEWARE"
    ],
    "examples": [
      "查询区域region_guian4下GaussDB实例按引擎版本分组数量和中间件按类型分组数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/MIDDLEWARE?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT engineVersion, COUNT(*) AS count FROM CLOUD_GAUSSDB_INSTANCE GROUP BY engineVersion UNION ALL SELECT type, COUNT(*) AS count FROM CLOUD_MIDDLEWARE GROUP BY type",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_157",
    "name": "tpl_157_CMDB-235",
    "description": "查询区域region_guian4下GaussDB实例数量和中间件实例数量",
    "resources": [
      "GAUSSDB_INSTANCE",
      "MIDDLEWARE"
    ],
    "examples": [
      "查询区域region_guian4下GaussDB实例数量和中间件实例数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/MIDDLEWARE?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT COUNT(*) AS gaussdb_count FROM CLOUD_GAUSSDB_INSTANCE UNION ALL SELECT COUNT(*) AS middleware_count FROM CLOUD_MIDDLEWARE",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_158",
    "name": "tpl_158_CMDB-236",
    "description": "查询CCE集群service-cm-cluster-roma-guian-4下的容器节点列表及节点IP",
    "resources": [
      "CCE_CLUSTER"
    ],
    "examples": [
      "查询CCE集群service-cm-cluster-roma-guian-4下的容器节点列表及节点IP"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CCE_CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_CCE_NODE.name AS node_name, CLOUD_CCE_NODE.privateIP AS node_ip, CLOUD_CCE_NODE.status AS status FROM CLOUD_CCE_CLUSTER INNER JOIN CLOUD_CCE_NODE ON CLOUD_CCE_CLUSTER.id = CLOUD_CCE_NODE.ref_clusterId",
    "default_params": {
      "name": "service-cm-cluster-roma-guian-4"
    }
  },
  {
    "id": "rb_159",
    "name": "tpl_159_CMDB-237",
    "description": "查询CCE工作负载列表",
    "resources": [
      "CCE_WORKLOAD"
    ],
    "examples": [
      "查询CCE工作负载列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CCE_WORKLOAD?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT DISTINCT CLOUD_CCE_WORKLOAD.name AS workload_name, CLOUD_CCE_WORKLOAD.managedStatus AS status FROM CLOUD_CCE_WORKLOAD"
  },
  {
    "id": "rb_160",
    "name": "tpl_160_CMDB-238",
    "description": "查询CCE集群service-cm-cluster-roma-guian-4下的Pod列表",
    "resources": [
      "CCE_CLUSTER"
    ],
    "examples": [
      "查询CCE集群service-cm-cluster-roma-guian-4下的Pod列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CCE_CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_CCE_POD.name AS pod_name, CLOUD_CCE_POD.managedStatus AS status FROM CLOUD_CCE_CLUSTER INNER JOIN CLOUD_CCE_POD ON CLOUD_CCE_CLUSTER.nativeId = CLOUD_CCE_POD.clusterId",
    "default_params": {
      "name": "service-cm-cluster-roma-guian-4"
    }
  },
  {
    "id": "rb_161",
    "name": "tpl_161_CMDB-239",
    "description": "查询CCE集群service-cm-cluster-roma-guian-4下容器节点列表",
    "resources": [
      "CCE_CLUSTER"
    ],
    "examples": [
      "查询CCE集群service-cm-cluster-roma-guian-4下容器节点列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/CCE_CLUSTER?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_CCE_NODE.name AS node_name, CLOUD_CCE_NODE.managedStatus AS status, CLOUD_CCE_NODE.cpu AS cpu FROM CLOUD_CCE_CLUSTER INNER JOIN CLOUD_CCE_NODE ON CLOUD_CCE_CLUSTER.nativeId = CLOUD_CCE_NODE.clusterId",
    "default_params": {
      "name": "service-cm-cluster-roma-guian-4"
    }
  },
  {
    "id": "rb_162",
    "name": "tpl_162_CMDB-241",
    "description": "查询ModelArts推理服务pool-aaaa及关联资源池和节点",
    "resources": [
      "MODELARTS_INF_SERVICE"
    ],
    "examples": [
      "查询ModelArts推理服务pool-aaaa及关联资源池和节点"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/MODELARTS_INF_SERVICE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_MODELARTS_INF_SERVICE.name AS service_name, CLOUD_MODELARTS_INF_POOL.name AS pool_name, CLOUD_MODELARTS_INF_NODE.name AS node_name FROM CLOUD_MODELARTS_INF_SERVICE INNER JOIN CLOUD_MODELARTS_INF_POOL ON CLOUD_MODELARTS_INF_SERVICE.ref_poolId = CLOUD_MODELARTS_INF_POOL.id INNER JOIN CLOUD_MODELARTS_INF_NODE ON CLOUD_MODELARTS_INF_POOL.id = CLOUD_MODELARTS_INF_NODE.ref_poolId",
    "default_params": {
      "name": "pool-aaaa"
    }
  },
  {
    "id": "rb_163",
    "name": "tpl_163_CMDB-243",
    "description": "查询ModelArts推理模型列表",
    "resources": [
      "MODELARTS_INF_MODEL"
    ],
    "examples": [
      "查询ModelArts推理模型列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/MODELARTS_INF_MODEL?pageNo=1&pageSize=10000"
    },
    "sql": "SELECT DISTINCT CLOUD_MODELARTS_INF_MODEL.name AS model_name, CLOUD_MODELARTS_TRAINING_JOB.name AS training_job_name FROM CLOUD_MODELARTS_INF_MODEL INNER JOIN CLOUD_MODELARTS_TRAINING_JOB ON CLOUD_MODELARTS_INF_MODEL.ref_trainingJobId = CLOUD_MODELARTS_TRAINING_JOB.id"
  },
  {
    "id": "rb_164",
    "name": "tpl_164_CMDB-244",
    "description": "查询区域region_guian4下ModelArts推理服务按状态分布",
    "resources": [
      "MODELARTS_INF_SERVICE"
    ],
    "examples": [
      "查询区域region_guian4下ModelArts推理服务按状态分布"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/MODELARTS_INF_SERVICE?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT status, COUNT(*) AS count FROM CLOUD_MODELARTS_INF_SERVICE GROUP BY status",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_165",
    "name": "tpl_165_CMDB-247",
    "description": "查询应用app-xy下各模块的名称和状态",
    "resources": [
      "Application"
    ],
    "examples": [
      "查询应用app-xy下各模块的名称和状态"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/Application?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT CLOUD_ApplicationModule.name AS module_name, CLOUD_ApplicationModule.status AS status FROM CLOUD_Application INNER JOIN CLOUD_ApplicationModule ON CLOUD_Application.id = CLOUD_ApplicationModule.appId",
    "default_params": {
      "name": "app-xy"
    }
  },
  {
    "id": "rb_166",
    "name": "tpl_166_CMDB-248",
    "description": "查询应用app-xy下的应用组件实例列表",
    "resources": [
      "Application"
    ],
    "examples": [
      "查询应用app-xy下的应用组件实例列表"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/Application?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "name",
              "value": "{{name}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT DISTINCT CLOUD_ApplicationModule.name AS module_name, CLOUD_ApplicationModuleIns.name AS instance_name FROM CLOUD_Application INNER JOIN CLOUD_ApplicationModule ON CLOUD_Application.id = CLOUD_ApplicationModule.appId INNER JOIN CLOUD_ApplicationModuleIns ON CLOUD_ApplicationModule.id = CLOUD_ApplicationModuleIns.appModuleId",
    "default_params": {
      "name": "app-xy"
    }
  },
  {
    "id": "rb_167",
    "name": "tpl_167_CMDB-249",
    "description": "查询应用app-xy下组件实例列表",
    "resources": [
      "Application",
      "ApplicationModule",
      "ApplicationModuleIns"
    ],
    "examples": [
      "查询应用app-xy下组件实例列表"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/Application?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ApplicationModule?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ApplicationModuleIns?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT CLOUD_ApplicationModuleIns.name AS instance_name, CLOUD_ApplicationModule.name AS module_name FROM CLOUD_Application INNER JOIN CLOUD_ApplicationModule ON CLOUD_Application.id = CLOUD_ApplicationModule.appId INNER JOIN CLOUD_ApplicationModuleIns ON CLOUD_ApplicationModule.id = CLOUD_ApplicationModuleIns.appModuleId",
    "default_params": {
      "name": "app-xy"
    }
  },
  {
    "id": "rb_168",
    "name": "tpl_168_CMDB-251",
    "description": "查询区域region_guian4下各可用区的ECS数量、云硬盘数量和VPC数量，按可用区分别展示",
    "resources": [
      "VM_NOVA",
      "VOLUME",
      "ROUTER"
    ],
    "examples": [
      "查询区域region_guian4下各可用区的ECS数量、云硬盘数量和VPC数量，按可用区分别展示"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT azoneName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY azoneName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_169",
    "name": "tpl_169_CMDB-252",
    "description": "查询租户AdvanceService_System_VDC在区域region_guian4中的ECS实例及规格、云硬盘列",
    "resources": [
      "VM_NOVA",
      "FLAVOR",
      "VOLUME"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC在区域region_guian4中的ECS实例及规格、云硬盘列表及容量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True,
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "id",
                "value": "{{flavorId from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT name AS volume_name, size AS volume_size, status AS volume_status FROM CLOUD_VOLUME",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_170",
    "name": "tpl_170_CMDB-253",
    "description": "查询区域region_guian4下各VDC的ECS数量、云硬盘数量和GaussDB实例数量",
    "resources": [
      "VM_NOVA",
      "VOLUME",
      "GAUSSDB_INSTANCE"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的ECS数量、云硬盘数量和GaussDB实例数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT vdcName, COUNT(*) AS volume_count FROM CLOUD_VOLUME GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_171",
    "name": "tpl_171_CMDB-255",
    "description": "查询VDCAdvanceService_Manage_VDC在区域region_guian4中的VPC、子网、弹性IP和",
    "resources": [
      "ROUTER",
      "SUBNET",
      "FLOATING_IPS",
      "SECURITY_GROUP"
    ],
    "examples": [
      "查询VDCAdvanceService_Manage_VDC在区域region_guian4中的VPC、子网、弹性IP和安全组数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS vpc_count FROM CLOUD_ROUTER",
    "default_params": {
      "vdcName": "AdvanceService_Manage_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_172",
    "name": "tpl_172_CMDB-256",
    "description": "查询区域region_guian4下各租户的ECS实例数量、云硬盘数量、云硬盘总容量和ECS规格分布",
    "resources": [
      "VM_NOVA",
      "VOLUME",
      "FLAVOR"
    ],
    "examples": [
      "查询区域region_guian4下各租户的ECS实例数量、云硬盘数量、云硬盘总容量和ECS规格分布"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True
      }
    ],
    "sql": "SELECT tenantName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY tenantName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_173",
    "name": "tpl_173_CMDB-258",
    "description": "查询区域region_guian4下各VDC的VPC、子网、弹性IP、安全组和ELB数量汇总",
    "resources": [
      "ROUTER",
      "SUBNET",
      "FLOATING_IPS",
      "SECURITY_GROUP",
      "ELB"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的VPC、子网、弹性IP、安全组和ELB数量汇总"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT vdcName, COUNT(*) AS sg_count FROM CLOUD_SECURITY_GROUP GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_174",
    "name": "tpl_174_CMDB-259",
    "description": "查询区域region_guian4下各可用区中异常状态ECS的实例名、IP、所属租户、所属集群和宿主机名，按可用区分组展",
    "resources": [
      "VM_NOVA",
      "HOST",
      "CLUSTER"
    ],
    "examples": [
      "查询区域region_guian4下各可用区中异常状态ECS的实例名、IP、所属租户、所属集群和宿主机名，按可用区分组展示"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "status",
                "value": "{{status}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/CLUSTER?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.azoneName, CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS ip, CLOUD_VM_NOVA.tenantName, CLOUD_CLUSTER.name AS cluster_name, CLOUD_HOST.name AS host_name FROM CLOUD_VM_NOVA LEFT JOIN CLOUD_CLUSTER ON CLOUD_VM_NOVA.clusterId = CLOUD_CLUSTER.id LEFT JOIN CLOUD_HOST ON CLOUD_VM_NOVA.hostId = CLOUD_HOST.id",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "status": "stopped"
    }
  },
  {
    "id": "rb_175",
    "name": "tpl_175_CMDB-260",
    "description": "查询区域region_guian4下各VDC的管理虚拟机名称、IP、所属云服务、规格和挂载云硬盘容量",
    "resources": [
      "VM_NOVA",
      "FLAVOR",
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的管理虚拟机名称、IP、所属云服务、规格和挂载云硬盘容量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "management",
                "value": "{{management}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.vdcName, CLOUD_VM_NOVA.name AS vm_name, SUM(CLOUD_VOLUME.size) AS total_volume_size FROM CLOUD_VM_NOVA INNER JOIN R_VOLUME_MOUNTON_VM ON R_VOLUME_MOUNTON_VM.vmId = CLOUD_VM_NOVA.id INNER JOIN CLOUD_VOLUME ON CLOUD_VOLUME.id = R_VOLUME_MOUNTON_VM.volumeId GROUP BY CLOUD_VM_NOVA.vdcName, CLOUD_VM_NOVA.name",
    "default_params": {
      "logicalRegionName": "region_guian4",
      "management": "True"
    }
  },
  {
    "id": "rb_176",
    "name": "tpl_176_CMDB-261",
    "description": "查询区域region_guian4下ECS数量最多的租户，列出该租户下所有ECS的IP和挂载云硬盘",
    "resources": [
      "VM_NOVA",
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4下ECS数量最多的租户，列出该租户下所有ECS的IP和挂载云硬盘"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT tenantName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY tenantName ORDER BY ecs_count DESC LIMIT 1",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_177",
    "name": "tpl_177_CMDB-262",
    "description": "查询区域region_guian4下云硬盘容量最大的VDC，列出该VDC的存储池详情",
    "resources": [
      "VOLUME",
      "STORAGE_POOL"
    ],
    "examples": [
      "查询区域region_guian4下云硬盘容量最大的VDC，列出该VDC的存储池详情"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT vdcName, SUM(size) AS total_size FROM CLOUD_VOLUME GROUP BY vdcName ORDER BY total_size DESC LIMIT 1"
  },
  {
    "id": "rb_178",
    "name": "tpl_178_CMDB-264",
    "description": "查询可用区az0.dc0下ECS数量最多的集群，列出该集群下所有宿主机的vCPU总量和运行中虚拟机",
    "resources": [
      "VM_NOVA",
      "CLUSTER",
      "HOST"
    ],
    "examples": [
      "查询可用区az0.dc0下ECS数量最多的集群，列出该集群下所有宿主机的vCPU总量和运行中虚拟机"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "azoneName",
                "value": "{{azoneName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/CLUSTER?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT clusterName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY clusterName",
    "default_params": {
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_179",
    "name": "tpl_179_CMDB-265",
    "description": "查询区域region_guian4下哪个VDC的ECS最多，该VDC中哪些ECS处于异常状态",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下哪个VDC的ECS最多，该VDC中哪些ECS处于异常状态"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT vdcName, COUNT(*) AS ecs_count FROM CLOUD_VM_NOVA GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_180",
    "name": "tpl_180_CMDB-267",
    "description": "查询应用app-xy下组件实例列表",
    "resources": [
      "Application",
      "ApplicationModule",
      "ApplicationModuleIns"
    ],
    "examples": [
      "查询应用app-xy下组件实例列表"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/Application?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "name",
                "value": "{{name}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ApplicationModule?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "appId",
                "value": "{{id from step 1}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ApplicationModuleIns?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "appModuleId",
                "value": "{{id from step 2}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT CLOUD_ApplicationModuleIns.name AS instance_name, CLOUD_ApplicationModuleIns.nativeId AS instance_id FROM CLOUD_ApplicationModuleIns",
    "default_params": {
      "name": "app-xy"
    }
  },
  {
    "id": "rb_181",
    "name": "tpl_181_CMDB-268",
    "description": "查询区域region_guian4下IP使用率最高的子网，列出该子网下所有端口的IP和MAC",
    "resources": [
      "SUBNET",
      "PORT"
    ],
    "examples": [
      "查询区域region_guian4下IP使用率最高的子网，列出该子网下所有端口的IP和MAC"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/PORT?pageNo=1&pageSize=10000",
        "autoPagination": True
      }
    ],
    "sql": "SELECT CLOUD_SUBNET.name AS subnet_name, CLOUD_SUBNET.cidr, COUNT(CLOUD_PORT.id) AS port_count FROM CLOUD_SUBNET LEFT JOIN R_PORT_IN_SUBNET ON CLOUD_SUBNET.id = R_PORT_IN_SUBNET.subnetId LEFT JOIN CLOUD_PORT ON CLOUD_PORT.id = R_PORT_IN_SUBNET.portId GROUP BY CLOUD_SUBNET.name, CLOUD_SUBNET.cidr ORDER BY port_count DESC LIMIT 1",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_182",
    "name": "tpl_182_CMDB-269",
    "description": "查询区域region_guian4下ECS实例名和租户",
    "resources": [
      "VM_NOVA",
      "FLAVOR"
    ],
    "examples": [
      "查询区域region_guian4下ECS实例名和租户"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.tenantName AS tenant_name FROM CLOUD_VM_NOVA",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_183",
    "name": "tpl_183_CMDB-270",
    "description": "查询区域region_guian4下云硬盘数量最多的租户，列出该租户的云硬盘名称和容量",
    "resources": [
      "VOLUME"
    ],
    "examples": [
      "查询区域region_guian4下云硬盘数量最多的租户，列出该租户的云硬盘名称和容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT name AS volume_name, size AS volume_size, status AS volume_status FROM CLOUD_VOLUME"
  },
  {
    "id": "rb_184",
    "name": "tpl_184_CMDB-271",
    "description": "查询VDCAdvanceService_Manage_VDC在区域region_guian4中各可用区的ECS运行中数量",
    "resources": [
      "VM_NOVA"
    ],
    "examples": [
      "查询VDCAdvanceService_Manage_VDC在区域region_guian4中各可用区的ECS运行中数量、停止数量和异常数量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "vdcName",
              "value": "{{vdcName}}",
              "operator": "equal"
            }
          },
          {
            "simple": {
              "name": "logicalRegionName",
              "value": "{{logicalRegionName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT azoneName, SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS running_count, SUM(CASE WHEN status = 'stopped' THEN 1 ELSE 0 END) AS stopped_count, SUM(CASE WHEN status NOT IN ('active', 'stopped', 'building') THEN 1 ELSE 0 END) AS error_count FROM CLOUD_VM_NOVA GROUP BY azoneName",
    "default_params": {
      "vdcName": "AdvanceService_Manage_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_185",
    "name": "tpl_185_CMDB-274",
    "description": "查询租户AdvanceService_System_VDC的ECS实例名和IP、云硬盘名称和容量、VPC名称列表",
    "resources": [
      "VM_NOVA",
      "VOLUME",
      "ROUTER"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC的ECS实例名和IP、云硬盘名称和容量、VPC名称列表"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT name AS volume_name, size AS volume_size, status AS volume_status FROM CLOUD_VOLUME",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC"
    }
  },
  {
    "id": "rb_186",
    "name": "tpl_186_CMDB-275",
    "description": "查询可用区az0.dc0下ELB数量、监听器总数和后端服务器成员总数",
    "resources": [
      "ELB",
      "LISTENER",
      "ELB_POOL_MEMBERS"
    ],
    "examples": [
      "查询可用区az0.dc0下ELB数量、监听器总数和后端服务器成员总数"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/LISTENER?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ELB_POOL_MEMBERS?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT COUNT(*) AS elb_count FROM CLOUD_ELB"
  },
  {
    "id": "rb_187",
    "name": "tpl_187_CMDB-281",
    "description": "查询租户AdvanceService_System_VDC的GaussDB实例列表、GaussDB节点列表和关联虚拟机列",
    "resources": [
      "GAUSSDB_INSTANCE",
      "GAUSSDB_NODE",
      "VM_NOVA"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC的GaussDB实例列表、GaussDB节点列表和关联虚拟机列表"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_NODE?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT CLOUD_VM_NOVA.name AS vm_name, CLOUD_VM_NOVA.privateIps AS ip, CLOUD_VM_NOVA.status FROM CLOUD_VM_NOVA INNER JOIN CLOUD_GAUSSDB_NODE ON CLOUD_VM_NOVA.id = CLOUD_GAUSSDB_NODE.ref_vmbmsId",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC"
    }
  },
  {
    "id": "rb_188",
    "name": "tpl_188_CMDB-282",
    "description": "查询区域region_guian4下物理设备总数、交换机数量和存储设备数量",
    "resources": [
      "S_Device",
      "S_Switch",
      "S_StorDevice"
    ],
    "examples": [
      "查询区域region_guian4下物理设备总数、交换机数量和存储设备数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/S_Device?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/S_Switch?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/S_StorDevice?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT COUNT(*) AS device_count FROM SYS_Device",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_189",
    "name": "tpl_189_CMDB-283",
    "description": "查询可用区az0.dc0下存储池数量、总容量、已用容量和可用容量",
    "resources": [
      "STORAGE_POOL"
    ],
    "examples": [
      "查询可用区az0.dc0下存储池数量、总容量、已用容量和可用容量"
    ],
    "api_call": {
      "method": "GET",
      "url": "/rest/hackthon/db/instances/STORAGE_POOL?pageNo=1&pageSize=10000",
      "condition": {
        "constraint": [
          {
            "simple": {
              "name": "azoneName",
              "value": "{{azoneName}}",
              "operator": "equal"
            }
          }
        ]
      }
    },
    "sql": "SELECT COUNT(*) AS pool_count, SUM(totalCapacityGB) AS total_capacity, SUM(allocatedCapacityGB) AS allocated_capacity, SUM(freeCapacityGB) AS free_capacity FROM CLOUD_STORAGE_POOL",
    "default_params": {
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_190",
    "name": "tpl_190_CMDB-284",
    "description": "查询区域region_guian4下各ModelArts推理服务数量、资源池数量和节点数量",
    "resources": [
      "MODELARTS_INF_SERVICE",
      "MODELARTS_INF_POOL",
      "MODELARTS_INF_NODE"
    ],
    "examples": [
      "查询区域region_guian4下各ModelArts推理服务数量、资源池数量和节点数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/MODELARTS_INF_SERVICE?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/MODELARTS_INF_POOL?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/MODELARTS_INF_NODE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS service_count FROM CLOUD_MODELARTS_INF_SERVICE",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_191",
    "name": "tpl_191_CMDB-285",
    "description": "查询租户AdvanceService_System_VDC在区域region_guian4中ECS的vCPU总核数、内存",
    "resources": [
      "VM_NOVA",
      "FLAVOR",
      "VOLUME"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC在区域region_guian4中ECS的vCPU总核数、内存总量和云硬盘总容量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT SUM(CLOUD_FLAVOR.vcpuSize) AS total_vcpu, SUM(CLOUD_FLAVOR.ramSize) AS total_ram FROM CLOUD_VM_NOVA INNER JOIN CLOUD_FLAVOR ON CLOUD_VM_NOVA.flavorId = CLOUD_FLAVOR.id",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_192",
    "name": "tpl_192_CMDB-287",
    "description": "查询VDCAdvanceService_Manage_VDC在区域region_guian4中各VPC的子网数量和弹性I",
    "resources": [
      "ROUTER",
      "SUBNET",
      "FLOATING_IPS"
    ],
    "examples": [
      "查询VDCAdvanceService_Manage_VDC在区域region_guian4中各VPC的子网数量和弹性IP数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ROUTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "vdcName",
                "value": "{{vdcName}}",
                "operator": "equal"
              }
            },
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SUBNET?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT name AS subnet_name FROM CLOUD_SUBNET",
    "default_params": {
      "vdcName": "AdvanceService_Manage_VDC",
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_193",
    "name": "tpl_193_CMDB-288",
    "description": "查询可用区az0.dc0下ELB列表、各ELB的监听器数量和后端服务器组成员数量",
    "resources": [
      "ELB",
      "LISTENER",
      "ELB_POOL",
      "ELB_POOL_MEMBERS"
    ],
    "examples": [
      "查询可用区az0.dc0下ELB列表、各ELB的监听器数量和后端服务器组成员数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ELB?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/LISTENER?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ELB_POOL?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/ELB_POOL_MEMBERS?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT name AS elb_name, ip AS elb_ip, status FROM CLOUD_ELB"
  },
  {
    "id": "rb_194",
    "name": "tpl_194_CMDB-289",
    "description": "查询租户AdvanceService_System_VDC的ECS实例列表、安全组列表和云硬盘列表",
    "resources": [
      "VM_NOVA",
      "SECURITY_GROUP",
      "VOLUME"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC的ECS实例列表、安全组列表和云硬盘列表"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/SECURITY_GROUP?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT name AS volume_name, size AS volume_size, status AS volume_status FROM CLOUD_VOLUME",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC"
    }
  },
  {
    "id": "rb_195",
    "name": "tpl_195_CMDB-290",
    "description": "查询可用区az0.dc0下宿主机列表、每台宿主机的VM数量和VM状态分布",
    "resources": [
      "HOST",
      "VM_NOVA"
    ],
    "examples": [
      "查询可用区az0.dc0下宿主机列表、每台宿主机的VM数量和VM状态分布"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "azoneName",
                "value": "{{azoneName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "azoneName",
                "value": "{{azoneName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT name AS host_name, ipAddress AS host_ip, status AS host_status FROM CLOUD_HOST",
    "default_params": {
      "azoneName": "az0.dc0"
    }
  },
  {
    "id": "rb_196",
    "name": "tpl_196_CMDB-291",
    "description": "查询区域region_guian4下GaussDB实例数量、中间件实例数量和OBS桶数量",
    "resources": [
      "GAUSSDB_INSTANCE",
      "MIDDLEWARE",
      "OBS_BUCKET"
    ],
    "examples": [
      "查询区域region_guian4下GaussDB实例数量、中间件实例数量和OBS桶数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_INSTANCE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/MIDDLEWARE?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/OBS_BUCKET?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS gaussdb_count FROM CLOUD_GAUSSDB_INSTANCE",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_197",
    "name": "tpl_197_CMDB-297",
    "description": "查询区域region_guian4下交换机数量、路由器数量和虚拟防火墙数量",
    "resources": [
      "S_Switch",
      "S_Router",
      "VFW"
    ],
    "examples": [
      "查询区域region_guian4下交换机数量、路由器数量和虚拟防火墙数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/S_Switch?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/S_Router?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VFW?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT COUNT(*) AS switch_count FROM SYS_Switch",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_198",
    "name": "tpl_198_CMDB-298",
    "description": "查询租户AdvanceService_System_VDC的ECS私有IP列表、关联弹性IP列表和所属宿主机列表",
    "resources": [
      "VM_NOVA",
      "FLOATING_IPS",
      "HOST"
    ],
    "examples": [
      "查询租户AdvanceService_System_VDC的ECS私有IP列表、关联弹性IP列表和所属宿主机列表"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLOATING_IPS?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "tenantName",
                "value": "{{tenantName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/HOST?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT floatingIpAddress AS floating_ip, status FROM CLOUD_FLOATING_IPS",
    "default_params": {
      "tenantName": "AdvanceService_System_VDC"
    }
  },
  {
    "id": "rb_199",
    "name": "tpl_199_CMDB-299",
    "description": "查询区域region_guian4下CCE集群列表、各集群的节点数量和各集群关联的虚拟机数量",
    "resources": [
      "CCE_CLUSTER",
      "CCE_NODE",
      "VM_NOVA"
    ],
    "examples": [
      "查询区域region_guian4下CCE集群列表、各集群的节点数量和各集群关联的虚拟机数量"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/CCE_CLUSTER?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/CCE_NODE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000"
      }
    ],
    "sql": "SELECT name AS cluster_name, status, clusterType FROM CLOUD_CCE_CLUSTER",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  },
  {
    "id": "rb_200",
    "name": "tpl_200_CMDB-300",
    "description": "查询区域region_guian4下各VDC的ECS总vCPU核数、云硬盘总容量和GaussDB节点总数",
    "resources": [
      "VM_NOVA",
      "FLAVOR",
      "VOLUME",
      "GAUSSDB_NODE"
    ],
    "examples": [
      "查询区域region_guian4下各VDC的ECS总vCPU核数、云硬盘总容量和GaussDB节点总数"
    ],
    "api_call": [
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VM_NOVA?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/FLAVOR?pageNo=1&pageSize=10000",
        "autoPagination": True
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/VOLUME?pageNo=1&pageSize=10000"
      },
      {
        "method": "GET",
        "url": "/rest/hackthon/db/instances/GAUSSDB_NODE?pageNo=1&pageSize=10000",
        "condition": {
          "constraint": [
            {
              "simple": {
                "name": "logicalRegionName",
                "value": "{{logicalRegionName}}",
                "operator": "equal"
              }
            }
          ]
        }
      }
    ],
    "sql": "SELECT vdcName, SUM(size) AS total_volume_size FROM CLOUD_VOLUME GROUP BY vdcName",
    "default_params": {
      "logicalRegionName": "region_guian4"
    }
  }
]