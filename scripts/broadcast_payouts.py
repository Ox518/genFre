#!/usr/bin/env python3
"""
Broadcast signed payout transactions via local daemon RPC.
Reads coin from the payout record and uses the matching daemon RPC credentials from pool.yaml.
Moves broadcast records to payouts/broadcast/.
"""
import json
import sys
import time
from pathlib import Path

import yaml
from bitcoinrpc.authproxy import AuthServiceProxy

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())

signed_dir = ROOT / "payouts/signed"
broadcast_dir = ROOT / "payouts/broadcast"
broadcast_dir.mkdir(parents=True, exist_ok=True)

for signed_file in sorted(signed_dir.glob("*.json")):
    broadcast_file = broadcast_dir / signed_file.name
    if broadcast_file.exists():
        continue

    try:
        payout = json.loads(signed_file.read_text())
        tx_hex = payout.get("tx_hex")
        if not tx_hex:
            print(f"[broadcast] {signed_file.name}: no tx_hex, skipping")
            continue

        coin_ticker = payout.get("coin", "").upper()
        coin_id = next((k for k, v in config["coins"].items() if v["ticker"] == coin_ticker), None)
        if not coin_id:
            print(f"[broadcast] {signed_file.name}: unknown coin {coin_ticker}, skipping")
            continue

        rpc_cfg = config["coins"][coin_id]["rpc"]
        rpc_url = f"http://{rpc_cfg['user']}:{rpc_cfg['pass']}@{rpc_cfg['host']}:{rpc_cfg['port']}"
        rpc = AuthServiceProxy(rpc_url, timeout=30)

        txid = rpc.sendrawtransaction(tx_hex)
        receipt = {**payout, "txid": txid, "broadcast_at": int(time.time())}
        broadcast_file.write_text(json.dumps(receipt, indent=2))
        print(f"[broadcast] {signed_file.name}: {coin_ticker} txid={txid}")

    except Exception as e:
        print(f"[broadcast] {signed_file.name}: ERROR {e}", file=sys.stderr)
