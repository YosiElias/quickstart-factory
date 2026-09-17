#!/usr/bin/env python3
"""Compute IDF-weighted relevance scores for KB index entries (Inverse Document Frequency).

Reads raw KB index files and an expanded-features JSON file (with aliases),
computes per-type IDF weights, scores each entry by tag match strength and
component name overlap, and writes enriched index files.

Usage:
    python3 core/scripts/idf-score-kb.py \\
        --index-dir .tmp/<slug>/kb-indexes \\
        --features-file .tmp/<slug>/expanded-features.json
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

import yaml

SUBDIRS = ["archetypes", "architectures", "components"]
TAG_KEYS = ["tech_stack", "ai_pattern", "platform", "data_layer"]


def load_features(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_lookup(expanded_features):
    """Build matching structures from expanded features.

    Returns:
    - component_map: alias_lower -> canonical component name (for name matching)
    - term_to_group: alias_lower -> canonical group key (for IDF grouping)

    Category-agnostic: tags from any input feature category can match
    tags in any entry tag category. Aliases of the same canonical term
    (e.g. k8s and kubernetes) are grouped so they count once for IDF.
    """
    component_map = {}
    term_to_group = {}

    for category, term_map in expanded_features.items():
        for canonical, aliases in term_map.items():
            group = canonical.lower()
            for alias in aliases:
                a = alias.lower()
                if a not in term_to_group:
                    term_to_group[a] = group
                if category == "components":
                    component_map[a] = canonical

    return component_map, term_to_group


def compute_idf(entries, term_to_group):
    """Compute per-type IDF for each canonical group.

    Aliases of the same term (e.g. k8s and kubernetes) are counted
    as a single group — if both appear in one entry, df increments once.
    """
    N = len(entries)
    if N == 0:
        return {}

    df = {}
    for entry in entries:
        seen = set()
        for key in TAG_KEYS:
            for tag in entry.get("tags", {}).get(key, []):
                group = term_to_group.get(tag.lower())
                if group and group not in seen:
                    seen.add(group)
                    df[group] = df.get(group, 0) + 1

    return {g: round(math.log(N / c), 3) for g, c in df.items()}


def score_entry(entry, component_map, term_to_group, idf):
    """Score one entry. Returns (idf_score, matching_tags, matching_components)."""
    matching_tags = []
    seen = set()
    score = 0.0

    for key in TAG_KEYS:
        for tag in entry.get("tags", {}).get(key, []):
            group = term_to_group.get(tag.lower())
            if group and group not in seen:
                seen.add(group)
                matching_tags.append(tag)
                score += idf.get(group, 0.0)

    name_tokens = set(re.split(r'[-_\s]+', entry.get("name", "").lower()))
    matching_components = sorted(
        {component_map[c] for c in component_map if c in name_tokens}
    )

    return round(score, 3), matching_tags, matching_components


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--features-file", type=Path, required=True)
    args = parser.parse_args()

    features = load_features(args.features_file)
    component_map, term_to_group = build_lookup(features)

    for subdir in SUBDIRS:
        index_file = args.index_dir / f"kb-index-{subdir}.yaml"
        if not index_file.exists():
            print(f"warning: {index_file} not found", file=sys.stderr)
            continue

        with open(index_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        entries = (data or {}).get("entries", [])

        idf = compute_idf(entries, term_to_group)

        enriched = []
        for entry in entries:
            s, mt, mc = score_entry(entry, component_map, term_to_group, idf)
            enriched.append({
                "name": entry["name"],
                "description": entry.get("description", ""),
                "tags": entry.get("tags", {}),
                "path": entry.get("path", ""),
                "idf_score": s,
                "matching_tags": mt,
                "matching_components": mc,
            })

        enriched.sort(key=lambda e: e["idf_score"], reverse=True)

        out = args.index_dir / f"scored-kb-index-{subdir}.yaml"
        out.write_text(
            yaml.dump(
                {"entries": enriched},
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        print(f"{out}: {len(enriched)} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
