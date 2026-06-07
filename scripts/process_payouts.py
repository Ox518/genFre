#!/usr/bin/env python3
"""
Process pending payouts using PPLNS share accounting.
Computes per-coin balances from validated shares, generates payout records.
Actual balance is queried via local daemon RPC — no simulated amounts.
Outputs: payouts/pending/{timestamp}-{coin}.json
"""
import json
import os
import sys
import time
from pathlib import Path

import yaml
from bitcoinrpc.authproxy import AuthServiceProxy

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())

stats_path = ROOT / "docs/stats.json"
if not stats_path.exists():
    print("[process_payouts] No stats.json. Run update_stats first.")
    exit(0)

stats = json.loads(stats_path.read_text())
miners = stats.get("miners", {})
total_shares = max(stats.get("total_shares", 1), 1)
force = os.environ.get("FORCE_PAYOUT", "false").lower() == "true"

(ROOT / "payouts/pending").mkdir(parents=True, exist_ok=True)

for coin_id, coin_cfg in config["coins"].items():
    ticker = coin_cfg["ticker"]
    rpc_cfg = coin_cfg["rpc"]
    fee_pct = coin_cfg.get("fee_percent", 1.0)
    threshold = 1.0  # minimum payout in coin units

    # Query actual pool balance via daemon RPC
    try:
        rpc_url = f"http://{rpc_cfg['user']}:{rpc_cfg['pass']}@{rpc_cfg['host']}:{rpc_cfg['port']}"
        rpc = AuthServiceProxy(rpc_url, timeout=15)
        pool_balance = float(rpc.getbalance())
        print(f"[process_payouts] {ticker} pool balance: {pool_balance:.8f}")
    except Exception as e:
        print(f"[process_payouts] {ticker}: RPC error: {e}", file=sys.stderr)
        continue

    if pool_balance <= 0:
        print(f"[process_payouts] {ticker}: zero balance, skipping")
        continue

    # Compute per-miner share fraction for this coin
    coin_shares_total = sum(
        m.get("coin_shares", {}).get(coin_id, 0) for m in miners.values()
    )
    if coin_shares_total == 0:
        print(f"[process_payouts] {ticker}: no shares yet, skipping")
        continue

    payable = pool_balance * (1 - fee_pct / 100)
    pending = []
    for addr, miner in miners.items():
        miner_coin_shares = miner.get("coin_shares", {}).get(coin_id, 0)
        if miner_coin_shares == 0:
            continue
        fraction = miner_coin_shares / coin_shares_total
        owed = round(payable * fraction, 8)
        if owed >= threshold or force:
            pending.append({"address": addr, "amount": owed, "shares": miner_coin_shares})

    if not pending:
        print(f"[process_payouts] {ticker}: no payouts above threshold ({threshold})")
        continue

    payout_record = {
        "id": f"{int(time.time())}-{coin_id}",
        "coin": ticker,
        "created_at": time.time(),
        "status": "pending",
        "pool_address": coin_cfg["address"],
        "payouts": pending,
        "total_out": sum(p["amount"] for p in pending),
        "fee_percent": fee_pct,
        "signatures": [],
    }
    payout_path = ROOT / f"payouts/pending/{payout_record['id']}.json"
    payout_path.write_text(json.dumps(payout_record, indent=2))
    print(f"[process_payouts] {ticker}: {len(pending)} recipients, total={payout_record['total_out']:.8f} {ticker}")
