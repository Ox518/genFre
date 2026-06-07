#!/usr/bin/env python3
"""Aggregate accepted shares into pool statistics."""
import argparse, json, subprocess, time
from pathlib import Path
from collections import defaultdict

def parse_share_commit(msg: str):
    if not msg.startswith("SHARE"):
        return None
    try:
        pipe = msg.find("|SIG")
        share_json = msg[5:pipe] if pipe != -1 else msg[5:]
        return json.loads(share_json)
    except Exception:
        return None

def get_accepted_shares(accepted_ref: str, lookback_commits=500):
    result = subprocess.run(
        ["git", "log", "--format=%H %ct %s", f"-{lookback_commits}", accepted_ref],
        capture_output=True, text=True
    )
    shares = []
    for line in result.stdout.strip().splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        sha, ts, msg = parts
        share = parse_share_commit(msg)
        if share:
            share["_sha"] = sha
            share["_ts"] = int(ts)
            shares.append(share)
    return shares

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accepted-ref", default="shares-accepted")
    ap.add_argument("--pool-config", required=True)
    ap.add_argument("--algo-config", required=True)
    ap.add_argument("--output-stats", required=True)   # docs/stats.json (public)
    ap.add_argument("--output-state", required=True)   # state/stats.json (full)
    args = ap.parse_args()

    import yaml
    pool_cfg = yaml.safe_load(Path(args.pool_config).read_text())["pool"]
    algo_cfg = yaml.safe_load(Path(args.algo_config).read_text())

    shares = get_accepted_shares(args.accepted_ref)
    now = int(time.time())
    window_1h = now - 3600
    window_24h = now - 86400

    miners = defaultdict(lambda: {"shares_1h": 0, "shares_24h": 0, "total_difficulty": 0, "last_seen": 0, "algo_counts": defaultdict(int)})
    algo_shares = defaultdict(int)
    algo_difficulty = defaultdict(float)

    for s in shares:
        miner = s.get("miner", "unknown")
        diff = float(s.get("difficulty", 1))
        algo = s.get("algo", "unknown")
        ts = s.get("_ts", 0)

        miners[miner]["total_difficulty"] += diff
        miners[miner]["last_seen"] = max(miners[miner]["last_seen"], ts)
        miners[miner]["algo_counts"][algo] += 1
        if ts >= window_1h:
            miners[miner]["shares_1h"] += 1
        if ts >= window_24h:
            miners[miner]["shares_24h"] += 1
        algo_shares[algo] += 1
        algo_difficulty[algo] += diff

    # Estimate hashrate (diff * 2^32 / time_window)
    def est_hashrate(diff_sum, window_secs):
        return (diff_sum * (2**32)) / window_secs if window_secs > 0 else 0

    pool_hashrate_1h = est_hashrate(sum(algo_difficulty[a] for a in algo_difficulty), 3600)

    public_stats = {
        "updated_at": now,
        "pool": {
            "name": pool_cfg.get("name"),
            "fee_percent": pool_cfg.get("fee_percent"),
            "hashrate_1h": round(pool_hashrate_1h, 2),
            "total_shares_24h": sum(1 for s in shares if s.get("_ts", 0) >= window_24h),
            "active_miners": len([m for m, v in miners.items() if v["last_seen"] >= window_1h]),
        },
        "algorithms": {
            algo: {
                "shares_24h": algo_shares[algo],
                "hashrate_1h": round(est_hashrate(algo_difficulty[algo], 3600), 2),
                "difficulty": algo_cfg["algorithms"].get(algo, {}).get("difficulty", 0),
            }
            for algo in ["sha256d", "scrypt", "myr-groestl"]
        },
        "miners": [
            {
                "address": addr,
                "shares_1h": data["shares_1h"],
                "shares_24h": data["shares_24h"],
                "hashrate_1h": round(est_hashrate(data["total_difficulty"], 3600), 2),
                "last_seen": data["last_seen"],
                "top_algo": max(data["algo_counts"], key=data["algo_counts"].get) if data["algo_counts"] else "?",
            }
            for addr, data in sorted(miners.items(), key=lambda x: x[1]["shares_24h"], reverse=True)
        ]
    }

    Path(args.output_stats).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_stats).write_text(json.dumps(public_stats, indent=2))
    Path(args.output_state).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_state).write_text(json.dumps(public_stats, indent=2))
    print(f"[update_stats] {len(shares)} shares, {len(miners)} miners, hashrate={pool_hashrate_1h:.0f} H/s")

if __name__ == "__main__":
    main()
