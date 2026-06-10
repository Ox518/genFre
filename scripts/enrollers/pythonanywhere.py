#!/usr/bin/env python3
"""
PythonAnywhere Zero-Auth Enroller
Free tier: always-on Python web app, no credit card required.
Uses PythonAnywhere API to create and schedule tasks.
"""
import requests, time, os

SCRIPT = """
import subprocess, os, sys
from pathlib import Path
POOL = os.environ.get('POOL_REPO', 'Ox518/genFre')
RIG  = os.environ.get('RIG_ID', 'pa-unknown')
if not Path('/tmp/genFre').exists():
    subprocess.run(['git', 'clone', f'https://github.com/{POOL}', '/tmp/genFre'], check=True)
os.chdir('/tmp/genFre')
subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '-q'])
subprocess.run([sys.executable, 'miner/git-mine-tty.py', '--rig-id', RIG, '--algo', 'auto', '--pool-repo', POOL])
"""

class PythonanywhereEnroller:
    API = 'https://www.pythonanywhere.com/api/v0/user/{user}'

    def __init__(self):
        self.token = os.environ.get('PYTHONANYWHERE_TOKEN', '')
        self.user  = os.environ.get('PYTHONANYWHERE_USER', '')

    def enroll(self, count, platform, secrets=None):
        workers = []
        if not self.token or not self.user:
            print('[pythonanywhere] token/user not set — skipping'); return workers
        base    = self.API.format(user=self.user)
        headers = {'Authorization': f'Token {self.token}'}
        pool    = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig  = f'pa-{self.user}-{int(time.time())}-{i}'
            path = f'/home/{self.user}/gitmine_harvest_{i}.py'
            try:
                # upload script
                requests.post(f'{base}/files/path{path}', headers=headers,
                    files={'content': ('script.py', SCRIPT.encode())})
                # schedule as always-on task
                r = requests.post(f'{base}/schedule/', headers=headers,
                    json={'command': f'python3 {path}',
                          'enabled': True, 'interval': 'daily',
                          'hour': 0, 'minute': 0,
                          'description': f'GitMine Harvest {i}'})
                if r.status_code in (200, 201):
                    workers.append({'id': rig, 'algo': 'auto', 'hashrate': '~30KH/s',
                        'expires_at': 'never',
                        'url': f'https://www.pythonanywhere.com/user/{self.user}/tasks/'})
                    print(f'[pythonanywhere] enrolled {rig}')
            except Exception as e:
                print(f'[pythonanywhere] error: {e}')
            time.sleep(3)
        return workers
