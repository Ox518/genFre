#!/usr/bin/env python3
"""
GitHub Anonymous Gist Worker
GitHub allows creating ANONYMOUS gists (no account/token needed)
via POST https://api.github.com/gists with no Authorization header.
We use anonymous gists as:
  1. Dead-drop config payloads for workers
  2. Lightweight heartbeat markers that update timestamps
  3. Worker registration receipts readable by the pool
Anonymous gists are public and permanent (until manually deleted).
"""
import requests, time, os, json
from datetime import datetime

GIST_API = 'https://api.github.com/gists'

class GithubGistWorkerEnroller:
    def create_anon_gist(self, rig_id, pool_repo):
        """Create an anonymous gist — no token, no account"""
        payload = {
            'description': f'GitMine Harvest Worker | {rig_id}',
            'public': True,
            'files': {
                'worker.json': {
                    'content': json.dumps({
                        'rig_id':    rig_id,
                        'pool_repo': pool_repo,
                        'enrolled':  datetime.utcnow().isoformat() + 'Z',
                        'algo':      'auto',
                        'status':    'active'
                    }, indent=2)
                },
                'heartbeat.sh': {
                    'content': (
                        '#!/bin/bash\n'
                        f'# GitMine Harvest heartbeat script for {rig_id}\n'
                        f'curl -s https://raw.githubusercontent.com/{pool_repo}/main/fleet/harvest/workers.yaml > /dev/null\n'
                        f'echo "heartbeat ok | rig={rig_id}"\n'
                    )
                }
            }
        }
        # Anonymous gist — no Authorization header needed
        headers = {'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        try:
            r = requests.post(GIST_API, headers=headers, json=payload, timeout=15)
            if r.status_code == 201:
                gist = r.json()
                return gist.get('id'), gist.get('html_url')
        except Exception as e:
            print(f'[gist] error: {e}')
        return None, None

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'gist-worker-{int(time.time())}-{i}'
            gist_id, url = self.create_anon_gist(rig, pool_repo)
            if gist_id:
                workers.append({
                    'id': rig, 'algo': 'gist_marker',
                    'hashrate': '~0KH/s', 'expires_at': 'never',
                    'url': url,
                    'note': f'Anonymous gist dead-drop. ID={gist_id}'
                })
                print(f'[gist] created anonymous gist {gist_id} -> {url}')
            time.sleep(1)
        return workers
