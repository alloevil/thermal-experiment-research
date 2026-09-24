"""Reject restored external reference bodies in this source-link public edition."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_references(root):
    registry = json.loads((root / "docs/reference-publication.json").read_text())
    seen = set()
    for entry in registry["entries"]:
        relative = entry["path"]
        require(relative not in seen, f"Duplicate reference: {relative}")
        seen.add(relative)
        if entry["action"] == "omitted_binary_with_source_notice":
            require(not (root / relative).exists(), f"Withheld binary restored: {relative}")
            path, expected = root / entry["notice_path"], entry["public_notice_sha256"]
        else:
            path, expected = root / relative, entry["public_sha256"]
        require(path.is_file() and not path.is_symlink(), f"Missing reference record: {relative}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"Public reference content changed: {relative}")
        if entry["action"] != "metadata_only_search_results":
            require(path.read_text().startswith("# External reference: content not redistributed"), f"Reference body instead of notice: {relative}")
            require(bool(entry["source_urls"]), f"No source URL retained: {relative}")
        else:
            def inspect(value):
                if isinstance(value, dict):
                    require(not {"abstract", "abstract_inverted_index", "description"}.intersection(value), "Quoted text reintroduced into search records")
                    for child in value.values():
                        inspect(child)
                elif isinstance(value, list):
                    for child in value:
                        inspect(child)
            inspect(json.loads(path.read_text()))
    for name in ["pde-LICENSE", "botorch-LICENSE"]:
        text = (root / "feasibility/upstream" / name).read_text()
        require("MIT License" in text and "Permission is hereby granted" in text, f"Missing upstream license: {name}")
    return len(seen)


if __name__ == "__main__":
    print(f"PASS {check_references(ROOT)} declared public reference transformations; upstream example licenses retained")
