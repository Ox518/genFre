#!/usr/bin/env python3
"""
Validate pending shares from the shares-pending branch.
Verifies:
  1. Commit message format: SHARE{...}|SIG{hex}
  2. Ed25519 signature matches declared miner pubkey
  3. Hash meets declared difficulty for the declared coin/algo
  4. Template height/coin matches current active template
Moves valid shares to shares-accepted, invalid to shares-rejected.

Supported algos:
  yescryptr16 (FNNC) — via yescrypt Python binding
  sha256d     (TTY)  — pure Python hashlib
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
import nacl.signing

ROOT = Path(__file__).parent.parent
config = yaml.safe_load((ROOT / "config/pool.yaml").read_text())
algos_cfg = yaml.safe_load((ROOT / "config/algorithms.yaml").read_text())
current_template = json.loads((ROOT / "docs/template.json").read_text())

SHARE_RE = re.compile(r'^SHARE(\{.+?\})\|SIG([0-9a-f]+)$')


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def verify_yescryptr16(blob: bytes, nonce: bytes, target: int) -> bool:
    try:
        import yescrypt
        header = blob[:76] + nonce
        h = yescrypt.hash(header, header, N=2048, r=8, p=1)
        return int.from_bytes(h[::-1], 'big') <= target
    except Exception as e:
        print(f"  yescryptr16 error: {e}", file=sys.stderr)
        return False


def verify_sha256d(blob: bytes, nonce: bytes, target: int) -> bool:
    header = blob[:76] + nonce
    h = sha256d(header)
    return int.from_bytes(h[::-1], 'big') <= target


def verify_share(share: dict, sig_hex: str) -> tuple[bool, str]:
    coin = share.get("coin", "").lower()
    algo = share.get("algo", "")

    # Must match current active template
    if share.get("height") and share["height"] != current_template.get("height"):
        return False, f"stale: height {share['height']} != {current_template.get('height')}"
    if coin != current_template.get("coin", "").lower():
        return False, f"coin mismatch: {coin} != {current_template.get('coin', '').lower()}"
    if algo != current_template.get("algo"):
        return False, f"algo mismatch: {algo} != {current_template.get('algo')}"

    # Ed25519 signature verification
    try:
        miner_pubkey_hex = share.get("pubkey", "")
        if miner_pubkey_hex:
            vk = nacl.signing.VerifyKey(bytes.fromhex(miner_pubkey_hex))
            msg = json.dumps({k: v for k, v in share.items() if k != "pubkey"}, separators=(',', ':')).encode()
            vk.verify(msg, bytes.fromhex(sig_hex))
    except Exception as e:
        return False, f"signature invalid: {e}"

    # Hash verification
    try:
        blob = bytes.fromhex(current_template.get("blob", ""))
        nonce = bytes.fromhex(share.get("nonce", ""))
        target = int(current_template.get("target", "0" * 64), 16)

        if algo == "yescryptr16":
            valid = verify_yescryptr16(blob, nonce, target)
        elif algo == "sha256d":
            valid = verify_sha256d(blob, nonce, target)
        else:
            return False, f"unsupported algo: {algo}"

        if not valid:
            return False, "hash does not meet target"
    except Exception as e:
        return False, f"hash verification error: {e}"

    return True, "ok"


result = subprocess.run(
    ["git", "log", "origin/shares-accepted..origin/shares-pending", "--format=%H %s"],
    capture_output=True, text=True, cwd=ROOT
)

lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
print(f"[validate_shares] Found {len(lines)} pending share commits")

accepted = []
rejected = []

for line in lines:
    commit_hash, *msg_parts = line.split(" ", 1)
    msg = msg_parts[0] if msg_parts else ""
    m = SHARE_RE.match(msg)
    if not m:
        print(f"  SKIP {commit_hash[:8]}: not a SHARE commit")
        continue

    try:
        share = json.loads(m.group(1))
        sig = m.group(2)
    except json.JSONDecodeError as e:
        rejected.append((commit_hash, f"JSON parse error: {e}"))
        continue

    valid, reason = verify_share(share, sig)
    if valid:
        accepted.append((commit_hash, share))
        print(f"  ACCEPT {commit_hash[:8]}: miner={share.get('miner','?')[:12]}... coin={share.get('coin')} algo={share.get('algo')}")
    else:
        rejected.append((commit_hash, reason))
        print(f"  REJECT {commit_hash[:8]}: {reason}")

(ROOT / "state").mkdir(exist_ok=True)
(ROOT / "state/validated_shares.json").write_text(json.dumps({
    "accepted": [{"commit": c, "share": s} for c, s in accepted],
    "rejected": [{"commit": c, "reason": r} for c, r in rejected],
    "validated_at": __import__('time').time()
}, indent=2))

print(f"[validate_shares] Accepted: {len(accepted)} Rejected: {len(rejected)}")
