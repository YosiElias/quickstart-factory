#!/usr/bin/env python3
"""Generate lean YAML indexes from the knowledge base frontmatter.

Mode 1 (default):
    python3 core/scripts/generate-kb-index.py --output-dir .tmp/<slug>/kb-indexes
    Generates 4 index files in the specified directory, one per KB subdirectory.

Mode 2:
    python3 core/scripts/generate-kb-index.py --extract-summaries path1.md path2.md ...
    Reads frontmatter of specified files (paths relative to KB root) and
    outputs a YAML mapping {path: summary} to stdout.
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

CORE_DIR = Path(__file__).resolve().parent.parent
KB_ROOT = CORE_DIR / "skills" / "qs-extract-knowledge" / "knowledge-base"

SUBDIRS = ["archetypes", "architectures", "components", "deployment"]

TAG_KEYS = ["tech_stack", "ai_pattern", "platform", "data_layer"]


def extract_frontmatter(filepath):
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    return yaml.safe_load(text[3:end])


def build_entry(fm, rel_path):
    tags = fm.get("tags", {}) or {}
    return {
        "name": fm.get("name", ""),
        "description": fm.get("description", ""),
        "tags": {k: tags.get(k, []) or [] for k in TAG_KEYS},
        "path": rel_path,
    }


def generate_indexes(output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for subdir in SUBDIRS:
        dir_path = KB_ROOT / subdir
        if not dir_path.is_dir():
            print(f"warning: {dir_path} not found, skipping", file=sys.stderr)
            continue

        entries = []
        for md_file in sorted(dir_path.glob("*.md")):
            try:
                fm = extract_frontmatter(md_file)
            except Exception as e:
                print(f"warning: {md_file.name}: {e}", file=sys.stderr)
                continue
            if fm is None:
                print(f"warning: {md_file.name}: no valid frontmatter", file=sys.stderr)
                continue
            rel_path = f"{subdir}/{md_file.name}"
            entries.append(build_entry(fm, rel_path))

        index_path = output_dir / f"kb-index-{subdir}.yaml"
        index_path.write_text(
            yaml.dump({"entries": entries}, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        print(f"{index_path}: {len(entries)} entries", file=sys.stderr)


def extract_summaries(paths):
    result = {}
    for rel in paths:
        filepath = KB_ROOT / rel
        if not filepath.exists():
            print(f"warning: {rel}: file not found", file=sys.stderr)
            continue
        try:
            fm = extract_frontmatter(filepath)
        except Exception as e:
            print(f"warning: {rel}: {e}", file=sys.stderr)
            continue
        if fm is None:
            print(f"warning: {rel}: no valid frontmatter", file=sys.stderr)
            continue
        result[rel] = fm.get("summary", "")

    sys.stdout.write(yaml.dump(result, default_flow_style=False, sort_keys=False, allow_unicode=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=False, help="Directory to write index files to (required for index generation)")
    parser.add_argument("--extract-summaries", nargs="+", metavar="PATH", help="Extract summaries for specific KB files (paths relative to KB root)")
    args = parser.parse_args()

    if args.extract_summaries:
        extract_summaries(args.extract_summaries)
    else:
        if not args.output_dir:
            parser.error("--output-dir is required for index generation")
        generate_indexes(args.output_dir)


if __name__ == "__main__":
    main()
