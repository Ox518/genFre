#!/usr/bin/env python3
"""
GitMine Zero-Auth Scavenger
Enrolls compute from platforms that don't require pre-configured secrets.
Runs automatically even with zero secrets. Attempts all platforms and
falls back gracefully if credentials aren't present.
"""
import yaml, os, importlib, time
from pathlib import Path
from datetime import datetime

PLATFORMS_FILE = Path('fleet/harvest/platforms_zeroauth.yaml')
REGISTRY_FILE  = Path('fleet/harvest/workers.yaml')

ORDER = [
    # no-secret-required first
    'glitch',
    # then optional-token platforms (will self-skip gracefully if no token)
    'cloudflare_workers',
    'deno_deploy',
    'netlify_functions',
    'vercel_functions',
    'aws_lambda_free',
    'github_codespaces',
    'pythonanywhere',
    'codesandbox',
    'supabase_edge',
]

def load_registry():
    data = yaml.safe_load(REGISTRY_FILE.read_text())
    return data if data else {'meta': {}, 'workers': []}

def save_registry(registry):
    registry['meta']['last_scan'] = datetime.utcnow().isoformat() + 'Z'
    registry['meta']['active_count'] = len(registry['workers'])
    REGISTRY_FILE.write_text(yaml.dump(registry, default_flow_style=False, sort_keys=False))

def load_enroller(name):
    try:
        mod = importlib.import_module(f'scripts.enrollers.{name}')
        cls = ''.join(w.capitalize() for w in name.split('_')) + 'Enroller'
        return getattr(mod, cls)()
    except Exception as e:
        print(f'[zeroauth] no enroller for {name}: {e}'); return None

def run(target=20):
    platforms = yaml.safe_load(PLATFORMS_FILE.read_text())['platforms_zeroauth']
    registry  = load_registry()
    existing  = {w['platform'] for w in registry['workers']}
    enrolled  = 0
    needed    = target - len(registry['workers'])
    if needed <= 0:
        print(f'[zeroauth] target met: {len(registry["workers"])} workers'); return
    print(f'[zeroauth] need {needed} more workers')
    for pname in ORDER:
        if enrolled >= needed: break
        p = platforms.get(pname)
        if not p: continue
        existing_on_platform = [w for w in registry['workers'] if w.get('platform') == pname]
        max_slots = p.get('max_workers', p.get('max_accounts', 5))
        slots = max_slots - len(existing_on_platform)
        if slots <= 0: continue
        enroller = load_enroller(pname)
        if not enroller: continue
        n = min(slots, needed - enrolled)
        print(f'[zeroauth] enrolling {n} on {pname}')
        try:
            new = enroller.enroll(n, p)
        except Exception as e:
            print(f'[zeroauth] {pname} error: {e}'); continue
        for w in new:
            registry['workers'].append({
                'id': w['id'], 'platform': pname,
                'enrolled_at': datetime.utcnow().isoformat() + 'Z',
                'last_heartbeat': datetime.utcnow().isoformat() + 'Z',
                'algo': w.get('algo', 'auto'),
                'estimated_hr': w.get('hashrate', 'unknown'),
                'expires_at': w.get('expires_at', 'never'),
                'url': w.get('url'), 'status': 'active'
            })
            enrolled += 1
            print(f'[zeroauth] enrolled {w["id"]} @ {pname}')
    save_registry(registry)
    print(f'[zeroauth] done — {enrolled} enrolled, {len(registry["workers"])} total')

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--target', type=int, default=20)
    args = p.parse_args()
    run(args.target)
