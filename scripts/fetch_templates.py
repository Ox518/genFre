#!/usr/bin/env python3
"""
Fetch block templates from both coin daemons.
FNNC: YescryptR16 via fennecd RPC (port 8339)
TTY:  SHA256d     via trinityd RPC (port 12345)
Outputs: config/templates/{coin}.json
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

output_dir = ROOT / "config/templates"
output_dir.mkdir(parents=True, exist_ok=True)

COIN_ENV = {
    "fnnc": ("FNNC_RPC_PASS", "FNNC_RPC_USER"),
    "tty":  ("TTY_RPC_PASS",  "TTY_RPC_USER"),
}

for coin_id, coin_cfg in config["coins"].items():
    pass_env, user_env = COIN_ENV[coin_id]
    rpc_user = os.environ.get(user_env, coin_cfg["rpc"]["user"])
    rpc_pass = os.environ[pass_env]
    rpc_url = f"http://{rpc_user}:{rpc_pass}@{coin_cfg['rpc']['host']}:{coin_cfg['rpc']['port']}"

    try:
        rpc = AuthServiceProxy(rpc_url, timeout=30)
        template = rpc.getblocktemplate({"capabilities": ["coinbasetxn", "workid", "coinbase/append"], "rules": []})
        template["coin"] = coin_id.upper()
        template["ticker"] = coin_cfg["ticker"]
        template["algo"] = coin_cfg["algo"]
        template["fetched_at"] = int(time.time())
        template["expires_at"] = int(time.time()) + config["template"]["ttl"]
        (output_dir / f"{coin_id}.json").write_text(json.dumps(template, indent=2))
        print(f"[fetch_templates] {coin_cfg['ticker']}/{coin_cfg['algo']}: height={template['height']} ok")
    except Exception as e:
        print(f"[fetch_templates] {coin_cfg['ticker']}: ERROR {e}", file=sys.stderr)
