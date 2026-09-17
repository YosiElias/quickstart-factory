#!/usr/bin/env python3
"""Select top-N KB entries per type and extract their summaries.

Reads the ranked KB entries file, selects top-N per type using defaults
or overrides, runs summary extraction via generate-kb-index.py, and
writes the combined output.

Usage:
    python3 core/scripts/select-top-kb.py \\
        --ranked-file .tmp/<slug>/kb-indexes/ranked-kb-entries.yaml \\
        --features-file .tmp/<slug>/expanded-features.json \\
        --output-file .tmp/<slug>/kb-indexes/top-kb-entries.yaml \\
        [--top-n-overrides '{"components": 10}'] \\
        [--deployment-questions-count 5]
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
KB_INDEX_SCRIPT = SCRIPT_DIR / "generate-kb-index.py"

DEFAULT_TOP_N = {
    "archetypes": 2,
    "architectures": 3,
    "deployment": 5,
    "components": 5,
}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ranked-file", type=Path, required=True)
    parser.add_argument("--features-file", type=Path, required=False, default=None)
    parser.add_argument("--output-file", type=Path, required=True)
    parser.add_argument("--top-n-overrides", type=str, default="{}")
    parser.add_argument("--deployment-questions-count", type=int, default=0)
    args = parser.parse_args()

    with open(args.ranked_file, encoding="utf-8") as f:
        ranked = yaml.safe_load(f) or {}

    if args.features_file and args.features_file.exists():
        with open(args.features_file, encoding="utf-8") as f:
            features = json.load(f)
    else:
        features = {}
    num_components = len(features.get("components", {}))

    overrides = json.loads(args.top_n_overrides)
    top_n = {
        "archetypes": overrides.get("archetypes", DEFAULT_TOP_N["archetypes"]),
        "architectures": overrides.get("architectures", DEFAULT_TOP_N["architectures"]),
        "components": overrides.get("components", max(DEFAULT_TOP_N["components"], math.ceil(num_components * 1.2))),
        "deployment": overrides.get("deployment", max(DEFAULT_TOP_N["deployment"], math.ceil(args.deployment_questions_count * 1.2))),
    }

    selected = {}
    all_paths = []
    for type_name, n in top_n.items():
        entries = ranked.get(type_name, [])
        top_entries = entries[:n]
        if top_entries:
            selected[type_name] = top_entries
            all_paths.extend(e["path"] for e in top_entries)

    summaries = {}
    if all_paths:
        result = subprocess.run(
            ["python3", str(KB_INDEX_SCRIPT), "--extract-summaries"] + all_paths,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            summaries = yaml.safe_load(result.stdout) or {}
        else:
            print(f"warning: extract-summaries failed: {result.stderr}", file=sys.stderr)

    for type_name, entries in selected.items():
        for entry in entries:
            entry["summary"] = summaries.get(entry["path"], "")

    active_top_n = {k: v for k, v in top_n.items() if k in selected}
    output = {"top_n": active_top_n, "results": selected}
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(
        yaml.dump(output, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"{args.output_file}: {sum(len(v) for v in selected.values())} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
