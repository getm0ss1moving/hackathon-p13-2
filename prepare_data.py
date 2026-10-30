"""检查根目录下发数据；可从同版本本地副本补齐缺失文件，不覆盖已有文件。"""

import argparse
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = Path("output-server/CI+md数据-脱敏-最终-0924")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE)
    args = parser.parse_args()
    source = args.source.resolve()
    manifest = json.loads((HERE / "baseline_manifest.json").read_text(encoding="utf-8"))
    targets = [Path(name) for name in manifest["readonly_files"]
               if name == "CMDB用例集-白盒200.json" or name.startswith(DATA_DIR.as_posix() + "/")]
    missing = [relative for relative in targets if not (HERE / relative).exists()]
    unavailable = [relative for relative in missing if not (source / relative).is_file()]
    if unavailable:
        parser.error("来源缺少下发数据，请用 --source 指定同版本仓库；首个缺失：" + str(unavailable[0]))
    copied = 0
    for relative in targets:
        target = HERE / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
            copied += 1
    print(f"数据就绪：复制 {copied} 个文件；已有文件保留。可运行 check_env.py 校验内容。")


if __name__ == "__main__":
    main()
