#!/usr/bin/env python3
import requests, time, os
from datetime import datetime, timedelta

class RenderEnroller:
    BASE = 'https://api.render.com/v1'
    def __init__(self):
        self.token = os.environ.get('RENDER_API_TOKEN','')
        self.headers = {'Authorization':f'Bearer {self.token}','Content-Type':'application/json'}
    def enroll(self, count, platform, secrets=None):
        workers = []
        if not self.token: print('[render] token not set'); return workers
        for i in range(count):
            name = f'gitmine-harvest-{int(time.time())}-{i}'
            rig  = f'render-{name}'
            try:
                r = requests.post(f'{self.BASE}/services',headers=self.headers,json={
                    'type':'background_worker','name':name,
                    'ownerId':os.environ.get('RENDER_OWNER_ID',''),
                    'repo':'https://github.com/Ox518/genFre','branch':'main',
                    'buildCommand':'pip install -r requirements.txt',
                    'startCommand':f'python miner/git-mine-tty.py --rig-id {rig} --algo scrypt',
                    'plan':'free',
                    'envVars':[{'key':'POOL_REPO','value':'Ox518/genFre'},
                               {'key':'RIG_ID','value':rig},
                               {'key':'DEPLOY_KEY','value':os.environ.get('HARVEST_DEPLOY_KEY','')}]})
                if r.status_code in (200,201):
                    workers.append({'id':rig,'algo':'scrypt','hashrate':'~60KH/s',
                        'expires_at':(datetime.utcnow()+timedelta(hours=750)).isoformat()+'Z',
                        'url':r.json().get('serviceDetails',{}).get('url','')})
            except Exception as e: print(f'[render] error: {e}')
            time.sleep(5)
        return workers
