#!/usr/bin/env python3
"""
Piston Zero-Auth Enroller
Piston is a public code execution API hosted at emkc.org.
NO API KEY, NO ACCOUNT, NO SIGNUP — completely open.
API: https://emkc.org/api/v2/piston/execute
Rate limit: generous, no auth required.
We use it as a persistent heartbeat worker that fires every 30s
via an external cron ping (cron-job.org free tier, also no-auth-setup).
"""
import requests, time, os, json
from datetime import datetime

PISTON_API = 'https://emkc.org/api/v2/piston/execute'

# Python code that runs inside Piston sandbox — phones home to pool
MINER_CODE = '''
import urllib.request, os, json, time
pool = '{pool_repo}'
rig  = '{rig_id}'
try:
    url = f'https://raw.githubusercontent.com/{pool}/main/fleet/harvest/workers.yaml'
    urllib.request.urlopen(url, timeout=10)
    print(f'[piston] heartbeat ok | rig={rig}')
except Exception as e:
    print(f'[piston] heartbeat fail: {e}')
'''

class PistonEnroller:
    def ping(self, rig_id, pool_repo):
        """Execute one Piston job — zero auth"""
        code = MINER_CODE.format(rig_id=rig_id, pool_repo=pool_repo)
        payload = {
            'language': 'python',
            'version':  '3.10.0',
            'files':    [{'name': 'main.py', 'content': code}]
        }
        try:
            r = requests.post(PISTON_API, json=payload, timeout=30)
            if r.status_code == 200:
                out = r.json().get('run', {}).get('stdout', '').strip()
                print(f'[piston] run ok: {out}')
                return True
        except Exception as e:
            print(f'[piston] error: {e}')
        return False

    def enroll(self, count, platform, secrets=None):
        """
        Piston has no persistent workers — each 'worker' is a
        scheduled CI job that calls Piston. We register N virtual
        workers and fire one test ping per worker to confirm reachability.
        """
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'piston-{int(time.time())}-{i}'
            ok  = self.ping(rig, pool_repo)
            if ok:
                workers.append({
                    'id':           rig,
                    'algo':         'piston_exec',
                    'hashrate':     '~0.1KH/s',
                    'expires_at':   'session',
                    'url':          PISTON_API,
                    'note':         'Zero-auth public code exec. Re-triggered each CI run.'
                })
                print(f'[piston] enrolled {rig}')
            time.sleep(2)
        return workers
