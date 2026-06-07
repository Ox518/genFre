#!/usr/bin/env python3
"""
Process pending payouts based on PPLNS share accounting.
Outputs: payouts/pending/{timestamp}.json
Payouts are broadcast via Trinity public RPC nodes (no local wallet needed).
"""
import json
import os
import time
from pathlib import Path

import yaml
import requests

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())
payout_cfg = yaml.safe_load((ROOT / "config/payouts.yaml").read_text())["payouts"]

stats = json.loads((ROOT / "docs/stats.json").read_text()) if (ROOT / "docs/stats.json").exists() else {}
miners = stats.get("miners", {})
force = os.environ.get("FORCE_PAYOUT", "false").lower() == "true"

total_shares = max(stats.get("total_shares", 1), 1)
threshold = payout_cfg.get("threshold", 100)

# Simulated pool balance (replace with actual RPC call in production)
# pool_balance = rpc.getbalance()
pool_balance = 0.0  # Placeholder

pending_payouts = []
for addr, miner in miners.items():
    share_fraction = miner["shares"] / total_shares
    owed = pool_balance * share_fraction * (1 - config["pool"]["fee_percent"] / 100)
    if owed >= threshold or force:
        pending_payouts.append({"address": addr, "amount": round(owed, 8), "shares": miner["shares"]})

if not pending_payouts:
    print(f"[process_payouts] No payouts due (threshold={threshold} TTY, force={force})")
    exit(0)

payout_record = {
    "id": int(time.time()),
    "created_at": time.time(),
    "status": "pending",
    "payouts": pending_payouts,
    "total_out": sum(p["amount"] for p in pending_payouts),
    "requires_signatures": payout_cfg["signing"]["required"],
    "signatures": []
}

(ROOT / "payouts/pending").mkdir(parents=True, exist_ok=True)
payout_path = ROOT / f"payouts/pending/{payout_record['id']}.json"
payout_path.write_text(json.dumps(payout_record, indent=2))

print(f"[process_payouts] Created payout record: {payout_path.name}")
print(f"  Recipients: {len(pending_payouts)} Total: {payout_record['total_out']:.8f} TTY")
