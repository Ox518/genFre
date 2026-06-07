#!/usr/bin/env python3
"""
Select the active template from available per-algo templates.
Rotation strategy: round-robin (default) or profitability.
Outputs: docs/template.json (served by GitHub Pages)
"""
import json
import os
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())
algos_cfg = yaml.safe_load((ROOT / "config/algorithms.yaml").read_text())

templates_dir = ROOT / "config/templates"
state_file = ROOT / "state/rotation_state.json"
state_file.parent.mkdir(parents=True, exist_ok=True)

# Load rotation state
if state_file.exists():
    rotation = json.loads(state_file.read_text())
else:
    rotation = {"last_algo": None, "algo_order": list(algos_cfg["algorithms"].keys()), "index": 0}

enabled_algos = [
    a for a, c in algos_cfg["algorithms"].items()
    if c.get("enabled") and (templates_dir / f"{a}.json").exists()
]

if not enabled_algos:
    print("[select_template] No templates available. Exiting.")
    exit(1)

# Round-robin selection
next_index = (rotation.get("index", 0)) % len(enabled_algos)
selected_algo = enabled_algos[next_index]
rotation["index"] = (next_index + 1) % len(enabled_algos)
rotation["last_algo"] = selected_algo

# Load and finalize template
template = json.loads((templates_dir / f"{selected_algo}.json").read_text())
template["selected_at"] = int(time.time())
template["expires_at"] = int(time.time()) + int(yaml.safe_load((ROOT / "config/pool.yaml").read_text())["template"]["ttl"])

# Write to docs/ (GitHub Pages)
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/template.json").write_text(json.dumps(template, indent=2))

# Persist rotation state
state_file.write_text(json.dumps(rotation, indent=2))

print(f"[select_template] Active: {selected_algo} height={template.get('height')}")
