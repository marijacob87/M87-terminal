#!/usr/bin/env python3
"""Exporta o planner local do M87 para o formato da PWA, sem alterar a origem."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.planner import PlannerStore


def normalize_text(value):
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item is not None)
    return str(value or "")


def normalize_task(task):
    return {
        "id": task.get("id") or str(uuid4()),
        "client": normalize_text(task.get("client", "")),
        "text": normalize_text(task.get("text", "")),
        "notes": normalize_text(task.get("notes", "")),
        "done": bool(task.get("done", False)),
        "tag": task.get("tag", ""),
        "updatedAt": task.get("updatedAt", 0),
    }


def export_data(storage_dir=None):
    store = PlannerStore(storage_dir)
    weeks = {}
    for key, source in store.data.get("weeks", {}).items():
        weeks[key] = {
            "start": source.get("start", key),
            "priorities": [normalize_task(task) for task in source.get("priorities", [])],
            "days": {
                day: [normalize_task(task) for task in tasks]
                for day, tasks in source.get("days", {}).items()
            },
            "notes": normalize_text(source.get("notes", "")),
        }
    return {
        "version": 1,
        "weeks": weeks,
        "approvals": [normalize_task(task) for task in store.data.get("approvals", [])],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = export_data(args.storage_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
