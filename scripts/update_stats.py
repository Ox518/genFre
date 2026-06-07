#!/usr/bin/env python3
"""
Aggregate validated shares into pool statistics.
Tracks per-coin, per-miner share counts, estimated hashrate, and balances.
Outputs: docs/stats.json, docs/payouts.json
"""
import json
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())
algos_cfg = yaml.safe_load((ROOT / "config/algorithms.yaml").read_text())

validated_path = ROOT / "state/validated_shares.json"
if not validated_path.exists():
    print("[update_stats] No validated shares file. Nothing to do.")
    exit(0)

validated = json.loads(validated_path.read_text())
now = int(time.time())

# Load or initialise stats
stats_path = ROOT / "docs/stats.json"
if stats_path.exists():
    stats = json.loads(stats_path.read_text())
else:
    stats = {
        "pool": {
            "name": config["pool"]["name"],
            "coins": [
                {"ticker": c["ticker"], "algo": c["algo"]}
                for c in config["coins"].values()
            ],
        },
        "coins": {coin_id: {"shares": 0, "hashrate": 0} for coin_id in config["coins"]},
        "miners": {},
        "total_shares": 0,
        "updated_at": 0,
    }

# Process accepted shares
for entry in validated.get("accepted", []):
    share = entry["share"]
    miner_addr = share.get("miner", "unknown")
    coin = share.get("coin", "UNKNOWN").lower()
    algo = share.get("algo", "unknown")
    diff = share.get("difficulty", 1)
    share_ts = share.get("ts", now)

    # Per-coin counters
    if coin not in stats["coins"]:
        stats["coins"][coin] = {"shares": 0, "hashrate": 0}
    stats["coins"][coin]["shares"] += 1

    # Per-miner record
    if miner_addr not in stats["miners"]:
        stats["miners"][miner_addr] = {
            "address": miner_addr,
            "shares": 0,
            "last_share_at": 0,
            "balance": 0.0,
            "paid_out": 0.0,
            "coin_shares": {},
            "rig": share.get("rig", "unknown"),
        }
    m = stats["miners"][miner_addr]
    m["shares"] += 1
    m["last_share_at"] = max(m["last_share_at"], share_ts)
    m["coin_shares"][coin] = m["coin_shares"].get(coin, 0) + 1

    stats["total_shares"] += 1

# Naive hashrate estimate: shares * difficulty / window (60s)
window = 60
for coin_id, coin_stats in stats["coins"].items():
    algo_cfg = algos_cfg["algorithms"].get(
        config["coins"].get(coin_id, {}).get("algo", ""), {}
    )
    diff = algo_cfg.get("difficulty", 1)
    recent = sum(
        1 for e in validated.get("accepted", [])
        if e["share"].get("coin", "").lower() == coin_id
        and now - e["share"].get("ts", 0) < window
    )
    coin_stats["hashrate"] = int(recent * diff / window)

stats["updated_at"] = now

(ROOT / "docs").mkdir(exist_ok=True)
stats_path.write_text(json.dumps(stats, indent=2))

# Write payouts.json (unpaid balances per miner per coin)
payouts_summary = [
    {
        "address": addr,
        "balance": m["balance"],
        "paid_out": m["paid_out"],
        "shares": m["shares"],
        "coin_shares": m["coin_shares"],
    }
    for addr, m in stats["miners"].items()
    if m["balance"] > 0 or m["shares"] > 0
]
(ROOT / "docs/payouts.json").write_text(json.dumps({"miners": payouts_summary, "updated_at": now}, indent=2))

print(f"[update_stats] miners={len(stats['miners'])} total_shares={stats['total_shares']}")
for cid, cs in stats["coins"].items():
    print(f"  {cid.upper()}: shares={cs['shares']} hashrate~={cs['hashrate']}H/s")
