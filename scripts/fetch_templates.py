#!/usr/bin/env python3
"""
Fetch block templates from both coin daemons.
RPC credentials are read directly from config/pool.yaml — no env vars needed.
FNNC: YescryptR16 via fennecd RPC (port 8339)
TTY:  SHA256d     via trinityd RPC (port 12345)
Outputs: config/templates/{coin}.json
"""
import json
import sys
import time
from pathlib import Path

import yaml
from bitcoinrpc.authproxy import AuthServiceProxy

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())

output_dir = ROOT / "config/templates"
output_dir.mkdir(parents=True, exist_ok=True)

for coin_id, coin_cfg in config["coins"].items():
    rpc = coin_cfg["rpc"]
    rpc_url = f"http://{rpc['user']}:{rpc['pass']}@{rpc['host']}:{rpc['port']}"
    try:
        client = AuthServiceProxy(rpc_url, timeout=30)
        template = client.getblocktemplate({"capabilities": ["coinbasetxn", "workid", "coinbase/append"], "rules": []})
        template["coin"] = coin_cfg["ticker"]
        template["algo"] = coin_cfg["algo"]
        template["fetched_at"] = int(time.time())
        template["expires_at"] = int(time.time()) + config["template"]["ttl"]
        (output_dir / f"{coin_id}.json").write_text(json.dumps(template, indent=2))
        print(f"[fetch_templates] {coin_cfg['ticker']}/{coin_cfg['algo']}: height={template['height']} ok")
    except Exception as e:
        print(f"[fetch_templates] {coin_cfg['ticker']}: ERROR {e}", file=sys.stderr)
