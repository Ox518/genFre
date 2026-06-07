#!/usr/bin/env python3
"""Monitor fleet heartbeats and write fleet status to state."""
import argparse, json, subprocess, time
from pathlib import Path

def get_last_heartbeat(rig_id: str) -> int:
    """Get unix timestamp of last heartbeat commit for a rig."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ct", "-1", f"origin/fleet/{rig_id}/heartbeat"],
            capture_output=True, text=True
        )
        ts = result.stdout.strip()
        return int(ts) if ts else 0
    except Exception:
        return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fleet-dir", required=True)
    ap.add_argument("--stats-output", required=True)
    ap.add_argument("--stale-threshold", default=90, type=int)  # seconds
    args = ap.parse_args()

    fleet_path = Path(args.fleet_dir)
    now = int(time.time())
    fleet_status = []

    for rig_dir in sorted(fleet_path.iterdir()):
        if not rig_dir.is_dir() or rig_dir.name == "rig-example":
            continue
        rig_id = rig_dir.name
        meta_file = rig_dir / "metadata.yaml"
        cfg_file = rig_dir / "config.yaml"

        import yaml
        metadata = yaml.safe_load(meta_file.read_text()) if meta_file.exists() else {}
        config = yaml.safe_load(cfg_file.read_text()) if cfg_file.exists() else {}

        last_hb = get_last_heartbeat(rig_id)
        age = now - last_hb if last_hb else 9999
        status = "online" if age < args.stale_threshold else ("stale" if age < 300 else "offline")

        fleet_status.append({
            "rig_id": rig_id,
            "status": status,
            "last_heartbeat": last_hb,
            "heartbeat_age_secs": age,
            "algo": config.get("miner", {}).get("algo", "?"),
            "owner": metadata.get("owner", "?"),
            "hardware": metadata.get("hardware", "?"),
        })
        print(f"[fleet] {rig_id}: {status} (last hb {age}s ago)")

    Path(args.stats_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.stats_output).write_text(json.dumps({"fleet": fleet_status, "updated_at": now}, indent=2))

if __name__ == "__main__":
    main()
