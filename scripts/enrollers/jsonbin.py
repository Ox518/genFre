#!/usr/bin/env python3
"""
jsonbin.io + Similar Zero-Auth REST Bins
Several free JSON storage APIs allow CREATE without auth:
  - jsonbin.io  (free tier, no key for public bins)
  - jsonhero.io (view/create public)
  - pastebin-style services with open APIs
We use these as heartbeat dead-drops and worker state stores.
Completely zero-auth for public bins.
"""
import requests, time, os, json
from datetime import datetime

class JsonbinEnroller:
    BINS = [
        {
            'name':    'jsonbin.io',
            'url':     'https://api.jsonbin.io/v3/b',
            'method':  'POST',
            'headers': {'Content-Type': 'application/json',
                        'X-Bin-Private': 'false'},
            'id_path': ['metadata', 'id'],
            'url_fmt': 'https://jsonbin.io/b/{id}'
        },
        {
            'name':    'api.npoint.io',
            'url':     'https://api.npoint.io/store',
            'method':  'POST',
            'headers': {'Content-Type': 'application/json'},
            'id_path': ['id'],
            'url_fmt': 'https://api.npoint.io/{id}'
        }
    ]

    def _nested_get(self, d, path):
        for k in path:
            d = d.get(k, {}) if isinstance(d, dict) else None
            if d is None: return None
        return d

    def create_bin(self, rig_id, pool_repo, bin_cfg):
        data = {
            'rig_id':    rig_id,
            'pool_repo': pool_repo,
            'enrolled':  datetime.utcnow().isoformat() + 'Z',
            'status':    'active'
        }
        try:
            r = requests.post(bin_cfg['url'], headers=bin_cfg['headers'],
                              json=data, timeout=15)
            if r.status_code in (200, 201):
                bid = self._nested_get(r.json(), bin_cfg['id_path'])
                if bid:
                    return bin_cfg['url_fmt'].format(id=bid)
        except Exception as e:
            print(f"[jsonbin:{bin_cfg['name']}] error: {e}")
        return None

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'jsonbin-{int(time.time())}-{i}'
            for bin_cfg in self.BINS:
                url = self.create_bin(rig, pool_repo, bin_cfg)
                if url:
                    workers.append({
                        'id': f"{rig}-{bin_cfg['name'].replace('.','_')}",
                        'algo': 'dead_drop',
                        'hashrate': '~0KH/s', 'expires_at': 'never',
                        'url': url,
                        'note': f"Zero-auth JSON dead-drop via {bin_cfg['name']}"
                    })
                    print(f"[jsonbin] created {rig} @ {bin_cfg['name']} -> {url}")
                    break
            time.sleep(1)
        return workers
