#!/usr/bin/env python3
"""
GitMine Scavenger — Free Compute Hunter
Scans, provisions, and maintains free internet compute nodes as supplement miners.
"""
import yaml, json, sys, time, argparse, importlib
from pathlib import Path
from datetime import datetime, timedelta

PLATFORMS_FILE = Path('fleet/harvest/platforms.yaml')
REGISTRY_FILE  = Path('fleet/harvest/workers.yaml')
LOGS_DIR       = Path('fleet/harvest/logs')
LOGS_DIR.mkdir(parents=True, exist_ok=True)

def load_platforms():
    return yaml.safe_load(PLATFORMS_FILE.read_text())['platforms']

def load_registry():
    data = yaml.safe_load(REGISTRY_FILE.read_text())
    return data if data else {'meta': {}, 'workers': []}

def save_registry(registry):
    registry['meta']['last_scan'] = datetime.utcnow().isoformat() + 'Z'
    registry['meta']['active_count'] = len(registry['workers'])
    REGISTRY_FILE.write_text(yaml.dump(registry, default_flow_style=False, sort_keys=False))

def log(tag, msg):
    line = f"{datetime.utcnow().isoformat()}Z [{tag}] {msg}"
    log_file = LOGS_DIR / f"{datetime.utcnow().strftime('%Y-%m-%d')}.log"
    with open(log_file, 'a') as f: f.write(line + '\n')
    print(line)

def parse_threshold(s):
    if s.endswith('hr'):  return timedelta(hours=int(s[:-2]))
    if s.endswith('min'): return timedelta(minutes=int(s[:-3]))
    if s.endswith('d'):   return timedelta(days=int(s[:-1]))
    return timedelta(hours=2)

def scan_and_prune(stale='2hr'):
    registry = load_registry()
    cutoff   = datetime.utcnow() - parse_threshold(stale)
    active   = []
    for w in registry['workers']:
        hb = w.get('last_heartbeat')
        if hb and datetime.fromisoformat(hb.rstrip('Z')) < cutoff:
            log('PRUNE', f"{w['id']} stale"); continue
        exp = w.get('expires_at', 'never')
        if exp and exp != 'never':
            try:
                if datetime.fromisoformat(exp.rstrip('Z')) < datetime.utcnow():
                    log('EXPIRE', f"{w['id']} expired"); continue
            except ValueError: pass
        active.append(w)
    pruned = len(registry['workers']) - len(active)
    registry['workers'] = active
    save_registry(registry)
    log('SCAN', f"Pruned {pruned}, {len(active)} active")
    return len(active)

def load_enroller(name):
    try:
        mod = importlib.import_module(f'scripts.enrollers.{name}')
        cls = ''.join(w.capitalize() for w in name.split('_')) + 'Enroller'
        return getattr(mod, cls)()
    except Exception as e:
        log('WARN', f"No enroller for {name}: {e}"); return None

def estimate_hr(workers):
    total = 0.0
    for w in workers:
        hr = str(w.get('estimated_hr', '0')).replace('~', '').strip()
        if 'MH' in hr:   total += float(hr.replace('MH/s', '')) * 1000
        elif 'KH' in hr: total += float(hr.replace('KH/s', ''))
    return f"~{total/1000:.1f} MH/s" if total >= 1000 else f"~{total:.0f} KH/s"

def enroll(target=50, secrets=None):
    registry  = load_registry()
    platforms = load_platforms()
    needed    = target - len(registry['workers'])
    if needed <= 0:
        log('INFO', f"Target met: {len(registry['workers'])} workers"); return
    log('INFO', f"Need {needed} more workers")
    order = ['oracle_cloud_free','fly_io','huggingface_spaces','replit',
             'google_colab','kaggle','render','github_actions','gitlab_ci']
    enrolled = 0
    for pname in order:
        if enrolled >= needed: break
        p = platforms.get(pname)
        if not p: continue
        existing  = [w for w in registry['workers'] if w['platform'] == pname]
        max_slots = p.get('max_accounts', p.get('max_spaces', p.get('max_repls', 5)))
        slots     = max_slots - len(existing)
        if slots <= 0: continue
        enroller = load_enroller(pname)
        if not enroller: continue
        n = min(slots, needed - enrolled)
        log('ENROLL', f"Enrolling {n} on {pname}")
        try:
            new = enroller.enroll(n, p, secrets=secrets)
        except Exception as e:
            log('ERROR', f"{pname}: {e}"); continue
        for w in new:
            registry['workers'].append({
                'id': w['id'], 'platform': pname,
                'enrolled_at': datetime.utcnow().isoformat()+'Z',
                'last_heartbeat': datetime.utcnow().isoformat()+'Z',
                'algo': w.get('algo','auto'),
                'estimated_hr': w.get('hashrate','unknown'),
                'expires_at': w.get('expires_at','never'),
                'url': w.get('url'), 'status': 'active'
            })
            enrolled += 1
            log('ENROLLED', f"{w['id']} @ {pname}")
    registry['meta']['total_hashrate_estimate'] = estimate_hr(registry['workers'])
    save_registry(registry)
    log('DONE', f"{enrolled} enrolled, {len(registry['workers'])} total")

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd')
    s = sub.add_parser('scan')
    s.add_argument('--registry', default='fleet/harvest/workers.yaml')
    s.add_argument('--prune-stale', default='2hr')
    e = sub.add_parser('enroll')
    e.add_argument('--platforms', default='fleet/harvest/platforms.yaml')
    e.add_argument('--registry',  default='fleet/harvest/workers.yaml')
    e.add_argument('--target-workers', type=int, default=50)
    e.add_argument('--secrets', type=json.loads, default={})
    args = p.parse_args()
    if args.cmd == 'scan':    scan_and_prune(args.prune_stale)
    elif args.cmd == 'enroll': enroll(target=args.target_workers, secrets=args.secrets)
    else: p.print_help()

if __name__ == '__main__': main()
