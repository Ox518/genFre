#!/usr/bin/env python3
"""
GitMine — Miner Client

Two ways to start:

  1. With a downloaded config file (easiest):
     python miner/git-mine.py --config ~/gitmine.json

  2. With flags (manual setup):
     python miner/git-mine.py --coin FNNC --address FYourAddress --rig rig-001
     (generates a keypair on first run, prints the pubkey to register on the dashboard)
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

ROOT = Path(__file__).parent.parent

ALGO_MAP = {'FNNC': 'yescryptr16', 'TTY': 'sha256d'}


# ─────────────────── Config loading

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def load_or_create_key(rig_id: str) -> tuple[bytes, str]:
    """Load or generate an Ed25519 key. Returns (private_key_bytes, public_key_hex)."""
    import nacl.signing, nacl.encoding
    key_dir = ROOT / f'fleet/{rig_id}/keys'
    key_dir.mkdir(parents=True, exist_ok=True)
    key_file = key_dir / 'signing.key'
    if key_file.exists():
        sk = nacl.signing.SigningKey(bytes.fromhex(key_file.read_text().strip()))
    else:
        sk = nacl.signing.SigningKey.generate()
        key_file.write_text(sk.encode(encoder=nacl.encoding.HexEncoder).decode())
        key_file.chmod(0o600)
        pubkey = sk.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
        print(f'[gitmine] Generated new keypair for {rig_id}')
        print(f'[gitmine] Public key: {pubkey}')
        print(f'[gitmine] Register this rig on the pool dashboard: {ROOT}/docs/index.html')
        print(f'[gitmine] Or visit: https://5mil.github.io/gitmine-tty')
    pubkey = sk.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    return sk, pubkey


def key_from_pkcs8_hex(hex_str: str):
    """Load Ed25519 signing key from PKCS8 hex (as exported by WebCrypto)."""
    import nacl.signing
    from cryptography.hazmat.primitives.serialization import load_der_private_key
    der = bytes.fromhex(hex_str)
    priv = load_der_private_key(der, password=None)
    raw = priv.private_bytes_raw()
    return nacl.signing.SigningKey(raw)


# ─────────────────── Hashing

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hash_sha256d(blob: bytes, nonce: int) -> bytes:
    return sha256d(blob[:76] + struct.pack('<I', nonce & 0xFFFFFFFF))


def hash_yescryptr16(blob: bytes, nonce: int) -> bytes:
    try:
        import yescrypt
        header = blob[:76] + struct.pack('<I', nonce & 0xFFFFFFFF)
        return yescrypt.hash(header, header, N=2048, r=8, p=1)
    except ImportError:
        raise RuntimeError('Install yescrypt: pip install yescrypt')


HASH_FN = {'sha256d': hash_sha256d, 'yescryptr16': hash_yescryptr16}


# ─────────────────── Template

def fetch_template(pool_url: str) -> dict | None:
    url = pool_url.rstrip('/') + '/template.json'
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'[gitmine] Template fetch failed: {e}', file=sys.stderr)
        return None


# ─────────────────── Share submission

def sign_share(share: dict, sk) -> str:
    import nacl.encoding
    payload = json.dumps({k: v for k, v in share.items() if k != 'pubkey'}, separators=(',', ':'))
    sig = sk.sign(payload.encode()).signature
    return sig.hex()


def submit_share(share: dict, sig: str, repo_path: Path) -> bool:
    msg = f'SHARE{json.dumps(share, separators=(",",":"))}|SIG{sig}'
    try:
        env = os.environ.copy()
        subprocess.run(['git', 'commit', '--allow-empty', '-m', msg],
                       cwd=repo_path, env=env, check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'HEAD:shares-pending'],
                       cwd=repo_path, env=env, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f'[gitmine] Push failed: {e.stderr.decode()}', file=sys.stderr)
        return False


# ─────────────────── Mining loop

def mine(coin: str, address: str, rig_id: str, pool_url: str, sk, pubkey_hex: str, threads: int = 1):
    algo = ALGO_MAP[coin.upper()]
    hash_fn = HASH_FN[algo]
    print(f'[gitmine] coin={coin} algo={algo} rig={rig_id} threads={threads}')
    print(f'[gitmine] address={address}')
    print(f'[gitmine] pubkey= {pubkey_hex}')

    template = None
    template_fetched_at = 0
    nonce = 0
    shares_found = 0
    start = time.time()

    while True:
        now = time.time()

        if template is None or (now - template_fetched_at) > 25:
            t = fetch_template(pool_url)
            if t:
                if template is None or t.get('height') != template.get('height') or t.get('coin') != template.get('coin'):
                    template = t
                    nonce = 0
                    print(f'[gitmine] template: {t.get("coin")} height={t.get("height")} algo={t.get("algo")}')
                template_fetched_at = now
            else:
                time.sleep(5)
                continue

        if template.get('coin', '').upper() != coin.upper():
            time.sleep(5)
            continue

        blob   = bytes.fromhex(template.get('blob', '00' * 76))
        target = int(template.get('target', 'f' * 64), 16)

        for _ in range(2000):
            h   = hash_fn(blob, nonce & 0xFFFFFFFF)
            val = int.from_bytes(h[::-1], 'big')
            if val <= target:
                share = {
                    'coin':       coin.upper(),
                    'algo':       algo,
                    'nonce':      struct.pack('<I', nonce & 0xFFFFFFFF).hex(),
                    'hash':       h.hex(),
                    'height':     template.get('height'),
                    'difficulty': template.get('difficulty', 0),
                    'miner':      address,
                    'pubkey':     pubkey_hex,
                    'rig':        rig_id,
                    'ts':         int(now),
                }
                sig = sign_share(share, sk)
                ok  = submit_share(share, sig, ROOT)
                if ok:
                    shares_found += 1
                    elapsed = time.time() - start
                    print(f'[gitmine] SHARE #{shares_found} nonce={share["nonce"]} hr={nonce/elapsed:.0f}H/s')
            nonce += 1

        if int(now) % 60 < 1:
            elapsed = time.time() - start
            print(f'[gitmine] nonce={nonce} hr={nonce/elapsed:.0f}H/s shares={shares_found}')


# ─────────────────── Entry

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='GitMine — Git-native CPU/GPU miner')
    ap.add_argument('--config',  help='Path to gitmine.json (downloaded from dashboard)')
    ap.add_argument('--coin',    choices=['FNNC', 'TTY'], help='Coin to mine')
    ap.add_argument('--address', help='Your payout address')
    ap.add_argument('--rig',     default='rig-001', help='Rig ID')
    ap.add_argument('--pool',    default='https://5mil.github.io/gitmine-tty', help='Pool URL')
    ap.add_argument('--threads', type=int, default=1, help='CPU threads')
    args = ap.parse_args()

    if args.config:
        cfg      = load_config(args.config)
        coin     = cfg['coin']
        address  = cfg['address']
        rig_id   = cfg.get('rig_id', 'rig-001')
        pool_url = cfg.get('pool', args.pool)
        threads  = cfg.get('threads', 1)
        sk       = key_from_pkcs8_hex(cfg['private_key'])
        import nacl.encoding
        pubkey_hex = sk.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    else:
        if not args.coin or not args.address:
            ap.error('Provide --config OR both --coin and --address')
        coin     = args.coin
        address  = args.address
        rig_id   = args.rig
        pool_url = args.pool
        threads  = args.threads
        sk, pubkey_hex = load_or_create_key(rig_id)

    try:
        mine(coin, address, rig_id, pool_url, sk, pubkey_hex, threads)
    except KeyboardInterrupt:
        print('\n[gitmine] Stopped.')
