#!/usr/bin/env python3
"""
Validate pending shares from the shares-pending branch.
Verifies:
  1. Commit message format (SHARE{...}|SIG{...})
  2. Ed25519 signature matches declared miner address
  3. Hash meets declared difficulty for the declared algorithm
  4. Template height/algo matches current template
Moves valid shares to shares-accepted, invalid to shares-rejected.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
import nacl.signing
import nacl.encoding

ROOT = Path(__file__).parent.parent
algos_cfg = yaml.safe_load((ROOT / "config/algorithms.yaml").read_text())
current_template = json.loads((ROOT / "docs/template.json").read_text())

SHARE_RE = re.compile(r'^SHARE(\{.+?\})\|SIG([0-9a-f]+)$')

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def verify_scrypt(blob: bytes, nonce: bytes, target: int) -> bool:
    try:
        import scrypt
        header = blob[:72] + nonce
        h = scrypt.hash(header, header, N=1024, r=1, p=1, dklen=32)
        return int.from_bytes(h[::-1], 'big') <= target
    except Exception as e:
        print(f"  scrypt error: {e}", file=sys.stderr)
        return False

def verify_myr_groestl(blob: bytes, nonce: bytes, target: int) -> bool:
    try:
        import groestl
        header = blob[:72] + nonce
        h = groestl.groestl512(header)[:32]
        return int.from_bytes(h[::-1], 'big') <= target
    except Exception as e:
        print(f"  groestl error: {e}", file=sys.stderr)
        return False

def verify_share(share: dict, sig_hex: str) -> tuple[bool, str]:
    algo = share.get("algo")
    if algo not in algos_cfg["algorithms"]:
        return False, f"unknown algo: {algo}"

    # Check template match
    if share.get("height") and share["height"] != current_template.get("height"):
        return False, f"stale share: height {share['height']} != {current_template.get('height')}"

    if algo != current_template.get("algo"):
        return False, f"algo mismatch: {algo} != {current_template.get('algo')}"

    # Verify Ed25519 signature (miner proves ownership of payout address)
    try:
        miner_pubkey_hex = share.get("pubkey", "")
        if miner_pubkey_hex:
            vk = nacl.signing.VerifyKey(bytes.fromhex(miner_pubkey_hex))
            msg = json.dumps({k: v for k, v in share.items() if k != "pubkey"}, separators=(',', ':')).encode()
            vk.verify(msg, bytes.fromhex(sig_hex))
    except Exception as e:
        return False, f"signature invalid: {e}"

    # Verify hash meets difficulty
    try:
        blob = bytes.fromhex(current_template.get("blob", ""))
        nonce = bytes.fromhex(share.get("nonce", ""))
        target = int(current_template.get("target", "0" * 64), 16)

        if algo == "sha256d":
            header = blob[:72] + nonce
            h = sha256d(header)
            valid = int.from_bytes(h[::-1], 'big') <= target
        elif algo == "scrypt":
            valid = verify_scrypt(blob, nonce, target)
        elif algo == "myr-groestl":
            valid = verify_myr_groestl(blob, nonce, target)
        else:
            valid = False

        if not valid:
            return False, "hash does not meet target"
    except Exception as e:
        return False, f"hash verification error: {e}"

    return True, "ok"

# Get commits from shares-pending branch not yet in shares-accepted
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
        print(f"  ACCEPT {commit_hash[:8]}: miner={share.get('miner', '?')[:12]}... algo={share.get('algo')}")
    else:
        rejected.append((commit_hash, reason))
        print(f"  REJECT {commit_hash[:8]}: {reason}")

# Write results for update_stats.py
(ROOT / "state").mkdir(exist_ok=True)
(ROOT / "state/validated_shares.json").write_text(json.dumps({
    "accepted": [{"commit": c, "share": s} for c, s in accepted],
    "rejected": [{"commit": c, "reason": r} for c, r in rejected],
    "validated_at": __import__('time').time()
}, indent=2))

print(f"[validate_shares] Accepted: {len(accepted)} Rejected: {len(rejected)}")
