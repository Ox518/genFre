#!/usr/bin/env python3
"""
Aggregate validated shares into pool statistics.
Outputs: docs/stats.json, docs/payouts.json
"""
import json
import time
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())
algos_cfg = yaml.safe_load((ROOT / "config/algorithms.yaml").read_text())

# Load validated shares
validated_path = ROOT / "state/validated_shares.json"
if not validated_path.exists():
    print("[update_stats] No validated shares file found. Nothing to do.")
    exit(0)

validated = json.loads(validated_path.read_text())

# Load existing stats or create fresh
stats_path = ROOT / "docs/stats.json"
existing = json.loads(stats_path.read_text()) if stats_path.exists() else {
    "pool": {"name": config["pool"]["name"], "ticker": config["pool"]["ticker"]},
    "miners": {},
    "algos": {a: {"shares": 0, "hashrate": 0} for a in algos_cfg["algorithms"]},
    "blocks": [],
    "total_shares": 0,
    "updated_at": 0,
}

# Accumulate new accepted shares
for entry in validated["accepted"]:
    share = entry["share"]
    miner = share.get("miner", "unknown")
    algo = share.get("algo", "unknown")
    diff = share.get("difficulty", 0)

    if miner not in existing["miners"]:
        existing["miners"][miner] = {
            "address": miner,
            "shares": 0,
            "last_share_at": 0,
            "earnings": 0.0,
            "algo_counts": {}
        }

    existing["miners"][miner]["shares"] += 1
    existing["miners"][miner]["last_share_at"] = int(time.time())
    existing["miners"][miner]["algo_counts"][algo] = existing["miners"][miner]["algo_counts"].get(algo, 0) + 1
    existing["algos"][algo]["shares"] = existing["algos"][algo].get("shares", 0) + 1
    existing["total_shares"] += 1

existing["updated_at"] = int(time.time())

# Write outputs
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/stats.json").write_text(json.dumps(existing, indent=2))

print(f"[update_stats] Stats updated. Total miners: {len(existing['miners'])} Total shares: {existing['total_shares']}")
