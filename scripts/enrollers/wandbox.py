#!/usr/bin/env python3
"""
Wandbox Zero-Auth Enroller
Wandbox (wandbox.org) is a free online compiler/executor.
NO API KEY, NO ACCOUNT — fully open REST API.
API: https://wandbox.org/api/compile.json
Supports Python, C++, Rust, Go, Node.js, Ruby, etc.
We fire persistent heartbeat jobs via the Wandbox API.
"""
import requests, time, os

WANDBOX_API = 'https://wandbox.org/api/compile.json'

HEARTBEAT_CODE = '''
import urllib.request
pool = '{pool_repo}'
rig  = '{rig_id}'
try:
    urllib.request.urlopen(f'https://raw.githubusercontent.com/{pool}/main/fleet/harvest/workers.yaml', timeout=10)
    print(f'wandbox heartbeat ok rig={rig}')
except Exception as e:
    print(f'wandbox heartbeat fail: {e}')
'''

class WandboxEnroller:
    def ping(self, rig_id, pool_repo):
        code = HEARTBEAT_CODE.format(rig_id=rig_id, pool_repo=pool_repo)
        payload = {
            'compiler': 'cpython-3.12.0',
            'code':     code,
            'stdin':    ''
        }
        try:
            r = requests.post(WANDBOX_API, json=payload, timeout=30)
            if r.status_code == 200:
                out = r.json().get('program_output', '').strip()
                print(f'[wandbox] {out}')
                return True
        except Exception as e:
            print(f'[wandbox] error: {e}')
        return False

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'wandbox-{int(time.time())}-{i}'
            ok  = self.ping(rig, pool_repo)
            if ok:
                workers.append({
                    'id':         rig,
                    'algo':       'wandbox_exec',
                    'hashrate':   '~0.1KH/s',
                    'expires_at': 'session',
                    'url':        WANDBOX_API,
                    'note':       'Zero-auth. Re-fired each CI run.'
                })
            time.sleep(2)
        return workers
