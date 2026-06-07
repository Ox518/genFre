#!/usr/bin/env python3
"""
Fetch block templates from Trinity daemon for all enabled algorithms.
Outputs: config/templates/{algo}.json
"""
import json
import os
import sys
import time
from pathlib import Path

import yaml
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())
algos_cfg = yaml.safe_load((ROOT / "config/algorithms.yaml").read_text())

rpc_url = (
    f"http://{os.environ['TRINITY_RPC_USER']}:{os.environ['TRINITY_RPC_PASS']}"
    f"@{config['pool']['rpc']['host']}:{config['pool']['rpc']['port']}"
)

output_dir = ROOT / "config/templates"
output_dir.mkdir(parents=True, exist_ok=True)

rpc = AuthServiceProxy(rpc_url, timeout=30)

for algo, algo_cfg in algos_cfg["algorithms"].items():
    if not algo_cfg.get("enabled", True):
        continue
    try:
        template = rpc.getblocktemplate({"capabilities": ["coinbasetxn", "workid", "coinbase/append"], "rules": []})
        template["algo"] = algo
        template["fetched_at"] = int(time.time())
        template["expires_at"] = int(time.time()) + config["template"]["ttl"]
        template["difficulty"] = algo_cfg["difficulty"]
        (output_dir / f"{algo}.json").write_text(json.dumps(template, indent=2))
        print(f"[fetch_templates] {algo}: height={template['height']} ok")
    except Exception as e:
        print(f"[fetch_templates] {algo}: ERROR {e}", file=sys.stderr)
