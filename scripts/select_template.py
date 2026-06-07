#!/usr/bin/env python3
"""
Select the active template — round-robin across enabled coins.
Outputs: docs/template.json (served by GitHub Pages to miners)
"""
import json
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())

templates_dir = ROOT / "config/templates"
state_file = ROOT / "state/rotation_state.json"
state_file.parent.mkdir(parents=True, exist_ok=True)

if state_file.exists():
    rotation = json.loads(state_file.read_text())
else:
    rotation = {"index": 0}

coins = [c for c in config["coins"].keys() if (templates_dir / f"{c}.json").exists()]

if not coins:
    print("[select_template] No templates available. Exiting.")
    exit(1)

selected = coins[rotation["index"] % len(coins)]
rotation["index"] = (rotation["index"] + 1) % len(coins)

template = json.loads((templates_dir / f"{selected}.json").read_text())
template["selected_at"] = int(time.time())
template["expires_at"] = int(time.time()) + config["template"]["ttl"]

(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/template.json").write_text(json.dumps(template, indent=2))
state_file.write_text(json.dumps(rotation, indent=2))

print(f"[select_template] Active: {template['ticker']}/{template['algo']} height={template.get('height')}")
