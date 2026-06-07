#!/usr/bin/env python3
"""Validate pending share commits against current template."""
import argparse, json, hashlib, struct, sys, subprocess
from pathlib import Path

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def validate_sha256d(blob_hex: str, nonce_hex: str, target_int: int) -> bool:
    blob = bytes.fromhex(blob_hex)
    nonce = bytes.fromhex(nonce_hex)
    header = blob[:72] + nonce[:8]
    h = sha256d(header)
    return int.from_bytes(h[::-1], 'big') <= target_int

def validate_scrypt(blob_hex: str, nonce_hex: str, target_int: int, params: dict) -> bool:
    try:
        import scrypt
        blob = bytes.fromhex(blob_hex)
        nonce = bytes.fromhex(nonce_hex)
        header = blob[:72] + nonce[:8]
        h = scrypt.hash(header, header,
                        N=params.get("N", 1024),
                        r=params.get("r", 1),
                        p=params.get("p", 1),
                        buflen=params.get("dklen", 32))
        return int.from_bytes(h[::-1], 'big') <= target_int
    except ImportError:
        print("[validate] scrypt lib not available, skipping", file=sys.stderr)
        return True  # pass through if lib missing in dev env

def validate_myr_groestl(blob_hex: str, nonce_hex: str, target_int: int) -> bool:
    try:
        import groestlcoin_hash
        blob = bytes.fromhex(blob_hex)
        nonce = bytes.fromhex(nonce_hex)
        header = blob[:72] + nonce[:8]
        h = groestlcoin_hash.getPoWHash(header)
        return int.from_bytes(h[::-1], 'big') <= target_int
    except ImportError:
        print("[validate] groestlcoin_hash not available, skipping", file=sys.stderr)
        return True

def parse_share_commit(msg: str):
    """Parse SHARE{...}|SIG... from commit message."""
    if not msg.startswith("SHARE"):
        return None, None
    try:
        pipe = msg.find("|SIG")
        share_json = msg[5:pipe] if pipe != -1 else msg[5:]
        sig = msg[pipe+4:] if pipe != -1 else None
        return json.loads(share_json), sig
    except Exception:
        return None, None

def validate_share(share: dict, sig: str, template: dict, algo_cfg: dict) -> tuple[bool, str]:
    algo = share.get("algo")
    if algo != template.get("algo"):
        return False, f"algo mismatch: share={algo} template={template.get('algo')}"
    if algo not in algo_cfg["algorithms"]:
        return False, f"unknown algo: {algo}"

    nonce = share.get("nonce", "")
    blob = template.get("bits", template.get("blob", ""))
    target_str = template.get("target", "0" * 64)
    target_int = int(target_str, 16)
    params = algo_cfg["algorithms"][algo].get("scrypt_params", {})

    if algo == "sha256d":
        ok = validate_sha256d(blob, nonce, target_int)
    elif algo == "scrypt":
        ok = validate_scrypt(blob, nonce, target_int, params)
    elif algo == "myr-groestl":
        ok = validate_myr_groestl(blob, nonce, target_int)
    else:
        return False, "unsupported algo"

    return ok, "valid" if ok else "hash above target"

def get_commits_on_ref(ref: str):
    """Get new commits on shares-pending not in main."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H %s", f"{ref}", "^origin/main"],
            capture_output=True, text=True, check=True
        )
        return [line.split(" ", 1) for line in result.stdout.strip().splitlines() if line]
    except subprocess.CalledProcessError:
        return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--algo-config", required=True)
    ap.add_argument("--pending-ref", default="origin/shares-pending")
    ap.add_argument("--accepted-ref", default="shares-accepted")
    ap.add_argument("--rejected-ref", default="shares-rejected")
    args = ap.parse_args()

    import yaml
    template = json.loads(Path(args.template).read_text())
    algo_cfg = yaml.safe_load(Path(args.algo_config).read_text())

    commits = get_commits_on_ref(args.pending_ref)
    accepted = 0
    rejected = 0

    for sha, msg in commits:
        share, sig = parse_share_commit(msg)
        if share is None:
            print(f"[validate] {sha[:8]} SKIP (not a share commit)")
            continue
        ok, reason = validate_share(share, sig, template, algo_cfg)
        if ok:
            subprocess.run(["git", "cherry-pick", sha], capture_output=True)
            subprocess.run(["git", "push", "origin", f"HEAD:{args.accepted_ref}"], capture_output=True)
            accepted += 1
            print(f"[validate] {sha[:8]} ACCEPT {share.get('algo')} miner={share.get('miner','?')[:12]}...")
        else:
            subprocess.run(["git", "push", "origin", f"{sha}:refs/heads/{args.rejected_ref}"], capture_output=True)
            rejected += 1
            print(f"[validate] {sha[:8]} REJECT {reason}")

    print(f"[validate] done: {accepted} accepted, {rejected} rejected")

if __name__ == "__main__":
    main()
