#!/usr/bin/env python3
import requests, time, os

class ReplitEnroller:
    GQL = 'https://replit.com/graphql'
    def __init__(self):
        self.token = os.environ.get('REPLIT_TOKEN','')
        self.headers = {'X-Requested-With':'XMLHttpRequest',
            'Cookie':f'connect.sid={self.token}','Content-Type':'application/json'}
    def enroll(self, count, platform, secrets=None):
        workers = []
        if not self.token: print('[replit] token not set'); return workers
        for i in range(count):
            name = f'gitmine-harvest-{int(time.time())}-{i}'
            rig  = f'replit-{name}'
            try:
                r = requests.post(self.GQL,headers=self.headers,json={
                    'query':'mutation C($i:CreateReplInput!){createRepl(input:$i){id slug url}}',
                    'variables':{'i':{'title':name,'language':'python3','isPrivate':True}}})
                url = r.json().get('data',{}).get('createRepl',{}).get('url','')
                if url:
                    workers.append({'id':rig,'algo':'auto','hashrate':'~30KH/s','expires_at':'never','url':url})
            except Exception as e: print(f'[replit] failed: {e}')
            time.sleep(5)
        return workers
