#!/usr/bin/env python3
"""一次性脚本：初始化 binsentinel-meta 仓库的目录结构。"""
import json
import sys
from pathlib import Path


def init_meta_repo(meta_path: str) -> None:
    root = Path(meta_path)
    (root / "queue" / "pending").mkdir(parents=True, exist_ok=True)
    (root / "queue" / "processing").mkdir(parents=True, exist_ok=True)
    (root / "queue" / "done").mkdir(parents=True, exist_ok=True)
    (root / "packages").mkdir(parents=True, exist_ok=True)

    state_file = root / "state.json"
    if not state_file.exists():
        state_file.write_text(
            json.dumps(
                {
                    "sources": {
                        "scoop-main": {"last_sha": None, "packages": {}},
                        "winget": {"last_sha": None, "packages": {}},
                    }
                },
                indent=2,
            )
        )
        print(f"已创建 {state_file}")
    else:
        print(f"{state_file} 已存在，跳过")

    gitkeep = root / "queue" / "processing" / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")

    index_file = root / "index.json"
    if not index_file.exists():
        index_file.write_text(json.dumps({"last_updated": None, "packages": {}}, indent=2))
        print(f"已创建 {index_file}")
    else:
        print(f"{index_file} 已存在，跳过")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法：python scripts/init_meta.py <元数据仓库路径>")
        sys.exit(1)
    init_meta_repo(sys.argv[1])
    print("完成。")
