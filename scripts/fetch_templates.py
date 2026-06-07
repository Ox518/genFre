#!/usr/bin/env python3
"""Fetch block templates from trinityd for all enabled algorithms."""
import argparse, json, os, sys, time
from pathlib import Path
import requests

ALGO_CAPS = {
    "sha256d":     {"capabilities": ["coinbasetxn", "workid"], "version": 1},
    "scrypt":      {"capabilities": ["coinbasetxn", "workid"], "version": 1},
    "myr-groestl": {"capabilities": ["coinbasetxn", "workid"], "version": 1},
}

def rpc(url, user, pwd, method, params=None):
    r = requests.post(url, json={"jsonrpc":"1.0","id":"gitmine","method":method,"params":params or []},
                      auth=(user, pwd), timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"RPC error: {data['error']}")
    return data["result"]

def fetch_template(rpc_url, user, pwd, algo):
    payload = {"rules": ["segwit"], **ALGO_CAPS[algo]}
    result = rpc(rpc_url, user, pwd, "getblocktemplate", [payload])
    result["algo"] = algo
    result["fetched_at"] = int(time.time())
    result["expires_at"] = int(time.time()) + 30
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc-host", default="127.0.0.1")
    ap.add_argument("--rpc-port", default=12345, type=int)
    ap.add_argument("--rpc-user", default=os.environ.get("TTY_RPC_USER", "user"))
    ap.add_argument("--rpc-pass", default=os.environ.get("TTY_RPC_PASS", "pass"))
    ap.add_argument("--algos", default="sha256d,scrypt,myr-groestl")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    rpc_url = f"http://{args.rpc_host}:{args.rpc_port}/"
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    algos = [a.strip() for a in args.algos.split(",")]
    for algo in algos:
        try:
            tpl = fetch_template(rpc_url, args.rpc_user, args.rpc_pass, algo)
            (out / f"{algo}.json").write_text(json.dumps(tpl, indent=2))
            print(f"[fetch_templates] {algo} height={tpl.get('height','?')} ok")
        except Exception as e:
            print(f"[fetch_templates] {algo} ERROR: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
