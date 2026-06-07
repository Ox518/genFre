#!/usr/bin/env python3
"""Compute pending payouts using PPLNS and write to payouts/pending/."""
import argparse, json, time
from pathlib import Path
from collections import defaultdict

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", required=True)
    ap.add_argument("--payout-config", required=True)
    ap.add_argument("--pool-address", required=True)
    ap.add_argument("--rpc-host", default="127.0.0.1")
    ap.add_argument("--rpc-port", default=12345, type=int)
    ap.add_argument("--rpc-user", default="user")
    ap.add_argument("--rpc-pass", default="pass")
    ap.add_argument("--pending-dir", required=True)
    args = ap.parse_args()

    import yaml
    payout_cfg = yaml.safe_load(Path(args.payout_config).read_text())["payouts"]
    stats = json.loads(Path(args.stats).read_text())
    threshold = float(payout_cfg.get("threshold", 100))
    fee = float(payout_cfg.get("tx_fee", 0.001))
    min_payout = float(payout_cfg.get("min_payout", 10))

    miners = stats.get("miners", [])
    pending = []

    # Load existing pending payouts to avoid double-paying
    pending_dir = Path(args.pending_dir)
    pending_dir.mkdir(parents=True, exist_ok=True)
    paid_addresses = set()
    for f in pending_dir.glob("*.json"):
        try:
            existing = json.loads(f.read_text())
            for p in existing.get("payouts", []):
                paid_addresses.add(p["address"])
        except Exception:
            pass

    for miner in miners:
        addr = miner["address"]
        if addr in paid_addresses or addr == args.pool_address:
            continue
        # Simplified: use share count as proxy for earnings
        # In production: use PPLNS window over block rewards
        shares_24h = miner.get("shares_24h", 0)
        if shares_24h == 0:
            continue
        # Placeholder earning calc (replace with actual block reward allocation)
        estimated_earnings = shares_24h * 0.01  # dummy: 0.01 TTY per share
        if estimated_earnings >= min_payout:
            pending.append({
                "address": addr,
                "amount": round(estimated_earnings - fee, 6),
                "shares_24h": shares_24h,
                "computed_at": int(time.time())
            })

    if pending:
        payout_file = pending_dir / f"{time.strftime('%Y-%m-%d-%H%M%S')}.json"
        payout_file.write_text(json.dumps({"payouts": pending, "created_at": int(time.time())}, indent=2))
        print(f"[process_payouts] {len(pending)} payout(s) queued: {payout_file.name}")
    else:
        print("[process_payouts] no payouts due")

if __name__ == "__main__":
    main()
