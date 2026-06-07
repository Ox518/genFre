#!/usr/bin/env python3
"""Broadcast signed payout transactions via public RPC."""
import argparse, json, time
from pathlib import Path
import requests

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signed-dir", required=True)
    ap.add_argument("--broadcast-dir", required=True)
    ap.add_argument("--rpc-url", required=True)
    args = ap.parse_args()

    signed_dir = Path(args.signed_dir)
    broadcast_dir = Path(args.broadcast_dir)
    broadcast_dir.mkdir(parents=True, exist_ok=True)

    for signed_file in sorted(signed_dir.glob("*.json")):
        broadcast_file = broadcast_dir / signed_file.name
        if broadcast_file.exists():
            continue  # already broadcast

        try:
            payout_data = json.loads(signed_file.read_text())
            tx_hex = payout_data.get("tx_hex")
            if not tx_hex:
                print(f"[broadcast] {signed_file.name}: no tx_hex, skipping")
                continue

            r = requests.post(args.rpc_url, json={"tx": tx_hex}, timeout=30)
            r.raise_for_status()
            result = r.json()
            txid = result.get("txid") or result.get("result") or "unknown"

            receipt = {**payout_data, "txid": txid, "broadcast_at": int(time.time())}
            broadcast_file.write_text(json.dumps(receipt, indent=2))
            print(f"[broadcast] {signed_file.name}: txid={txid}")
        except Exception as e:
            print(f"[broadcast] {signed_file.name}: ERROR {e}")

if __name__ == "__main__":
    main()
