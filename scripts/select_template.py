#!/usr/bin/env python3
"""Select the next active template via round-robin or profitability."""
import argparse, json, os
from pathlib import Path
import yaml

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates-dir", required=True)
    ap.add_argument("--algo-config", required=True)
    ap.add_argument("--stats-file", default="state/stats.json")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    algo_cfg = yaml.safe_load(Path(args.algo_config).read_text())
    mode = algo_cfg.get("selection_mode", "round_robin")
    enabled = [a for a, v in algo_cfg["algorithms"].items() if v.get("enabled", True)]

    # Load existing template to determine last algo
    last_algo = None
    out_path = Path(args.output)
    if out_path.exists():
        try:
            last_algo = json.loads(out_path.read_text()).get("algo")
        except Exception:
            pass

    if mode == "fixed":
        chosen = algo_cfg.get("fixed_algo", enabled[0])
    elif mode == "round_robin":
        if last_algo in enabled:
            idx = (enabled.index(last_algo) + 1) % len(enabled)
        else:
            idx = 0
        chosen = enabled[idx]
    else:
        chosen = enabled[0]  # fallback

    tpl_file = Path(args.templates_dir) / f"{chosen}.json"
    if not tpl_file.exists():
        # Fall back to any available template
        available = list(Path(args.templates_dir).glob("*.json"))
        if not available:
            raise FileNotFoundError("No templates available")
        tpl_file = available[0]

    tpl = json.loads(tpl_file.read_text())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(tpl, indent=2))
    print(f"[select_template] chose {tpl.get('algo')} height={tpl.get('height','?')}")

if __name__ == "__main__":
    main()
