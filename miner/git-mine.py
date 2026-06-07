#!/usr/bin/env python3
"""
GitMine — Miner Client
Polls the pool template from GitHub Pages, hashes with the correct algo,
and submits shares as signed git commits to shares-pending.

Usage:
  python miner/git-mine.py --coin FNNC --address FYourFennecAddress --rig rig-001
  python miner/git-mine.py --coin TTY  --address TYourTrinityAddress --rig rig-001

First run: generates an Ed25519 keypair in fleet/<rig-id>/keys/ and prints the pubkey.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import requests
import nacl.signing
import nacl.encoding

ROOT = Path(__file__).parent.parent

ALGO_MAP = {
    "FNNC": "yescryptr16",
    "TTY":  "sha256d",
}

# ─────────────────────────── Key management

def load_or_create_keypair(rig_id: str) -> nacl.signing.SigningKey:
    key_dir = ROOT / f"fleet/{rig_id}/keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    key_file = key_dir / "signing.key"
    if key_file.exists():
        sk = nacl.signing.SigningKey(bytes.fromhex(key_file.read_text().strip()))
    else:
        sk = nacl.signing.SigningKey.generate()
        key_file.write_text(sk.encode(encoder=nacl.encoding.HexEncoder).decode())
        key_file.chmod(0o600)
        print(f"[gitmine] Generated new keypair for {rig_id}")
        print(f"[gitmine] Public key: {sk.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()}")
        print(f"[gitmine] Add this rig to the pool by committing fleet/{rig_id}/config.yaml")
    return sk


# ─────────────────────────── Template fetching

def fetch_template(pages_base: str) -> dict | None:
    url = f"{pages_base.rstrip('/')}/template.json"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[gitmine] Template fetch failed: {e}", file=sys.stderr)
        return None


# ─────────────────────────── Hashing

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hash_sha256d(blob: bytes, nonce: int) -> bytes:
    header = blob[:76] + struct.pack('<I', nonce)
    return sha256d(header)


def hash_yescryptr16(blob: bytes, nonce: int) -> bytes:
    try:
        import yescrypt
        header = blob[:76] + struct.pack('<I', nonce)
        return yescrypt.hash(header, header, N=2048, r=8, p=1)
    except ImportError:
        raise RuntimeError("yescrypt package not installed. Run: pip install yescrypt")


HASH_FN = {
    "sha256d":      hash_sha256d,
    "yescryptr16":  hash_yescryptr16,
}


# ─────────────────────────── Share signing + submission

def sign_share(share: dict, sk: nacl.signing.SigningKey) -> str:
    payload = json.dumps({k: v for k, v in share.items() if k != "pubkey"}, separators=(',', ':'))
    sig = sk.sign(payload.encode()).signature
    return sig.hex()


def submit_share(share: dict, sig: str) -> bool:
    msg = f'SHARE{json.dumps(share, separators=(",",":"))}|SIG{sig}'
    try:
        env = os.environ.copy()
        subprocess.run(["git", "checkout", "--orphan", "tmp-share"], cwd=ROOT, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", msg], cwd=ROOT, env=env, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "HEAD:shares-pending"], cwd=ROOT, env=env, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=ROOT, capture_output=True)
        subprocess.run(["git", "branch", "-D", "tmp-share"], cwd=ROOT, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[gitmine] Share push failed: {e.stderr.decode()}", file=sys.stderr)
        subprocess.run(["git", "checkout", "main"], cwd=ROOT, capture_output=True)
        return False


# ─────────────────────────── Mining loop

def mine(coin: str, address: str, rig_id: str, pages_base: str, threads: int = 1):
    algo = ALGO_MAP[coin.upper()]
    sk = load_or_create_keypair(rig_id)
    pubkey_hex = sk.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    hash_fn = HASH_FN[algo]

    print(f"[gitmine] Starting miner: coin={coin} algo={algo} rig={rig_id}")
    print(f"[gitmine] Address: {address}")
    print(f"[gitmine] Pubkey:  {pubkey_hex}")

    template = None
    template_fetched_at = 0
    nonce = 0
    shares_found = 0
    start = time.time()

    while True:
        now = time.time()

        # Refresh template every 30s or when expired
        if template is None or (now - template_fetched_at) > 25:
            new_template = fetch_template(pages_base)
            if new_template:
                if template is None or new_template.get("height") != template.get("height") \
                        or new_template.get("coin") != template.get("coin"):
                    template = new_template
                    nonce = 0
                    print(f"[gitmine] New template: {template.get('coin')} height={template.get('height')} algo={template.get('algo')}")
                template_fetched_at = now
            else:
                time.sleep(5)
                continue

        # Only mine if this template matches our coin
        if template.get("coin", "").upper() != coin.upper():
            time.sleep(5)
            continue

        blob = bytes.fromhex(template.get("blob", "0" * 152))
        target = int(template.get("target", "0" * 64), 16)

        # Hash batch
        for _ in range(1000):
            h = hash_fn(blob, nonce & 0xFFFFFFFF)
            val = int.from_bytes(h[::-1], 'big')
            if val <= target:
                difficulty = template.get("difficulty", 0)
                share = {
                    "coin": coin.upper(),
                    "algo": algo,
                    "nonce": struct.pack('<I', nonce & 0xFFFFFFFF).hex(),
                    "hash": h.hex(),
                    "height": template.get("height"),
                    "difficulty": difficulty,
                    "miner": address,
                    "pubkey": pubkey_hex,
                    "rig": rig_id,
                    "ts": int(now),
                }
                sig = sign_share(share, sk)
                ok = submit_share(share, sig)
                if ok:
                    shares_found += 1
                    elapsed = time.time() - start
                    hashrate = (nonce / elapsed) if elapsed > 0 else 0
                    print(f"[gitmine] SHARE #{shares_found} submitted! nonce={share['nonce']} hashrate={hashrate:.0f}H/s")
            nonce += 1

        # Heartbeat every 60s
        if int(now) % 60 < 2:
            elapsed = time.time() - start
            hashrate = (nonce / elapsed) if elapsed > 0 else 0
            print(f"[gitmine] nonce={nonce} hashrate={hashrate:.0f}H/s shares={shares_found}")


# ─────────────────────────── Entrypoint

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GitMine — Git-native CPU/GPU miner")
    ap.add_argument("--coin",    required=True,  choices=["FNNC", "TTY"], help="Coin to mine")
    ap.add_argument("--address", required=True,  help="Your payout address")
    ap.add_argument("--rig",     default="rig-001", help="Rig ID (default: rig-001)")
    ap.add_argument("--pool",    default="https://5mil.github.io/gitmine-tty", help="Pool Pages base URL")
    args = ap.parse_args()

    try:
        mine(args.coin, args.address, args.rig, args.pool)
    except KeyboardInterrupt:
        print("\n[gitmine] Stopped.")
