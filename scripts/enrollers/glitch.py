#!/usr/bin/env python3
"""
Glitch.com Zero-Auth Enroller
Free tier: always-on Node.js/Python apps, no login required via API.
Uses Glitch's unofficial project-creation API (no auth for public remix).
Auto-remixes the gitmine-harvest template project.
"""
import requests, time, os
from datetime import datetime, timedelta

TEMPLATE_DOMAIN = 'gitmine-harvest-template'

class GlitchEnroller:
    API = 'https://api.glitch.com'

    def __init__(self):
        self.token = os.environ.get('GLITCH_AUTH_TOKEN', '')

    def _headers(self):
        h = {'Content-Type': 'application/json'}
        if self.token:
            h['Authorization'] = self.token
        return h

    def remix_project(self, template_domain):
        r = requests.post(f'{self.API}/v1/projects/{template_domain}/remix',
            headers=self._headers())
        if r.status_code in (200, 201):
            return r.json()
        return None

    def set_env(self, project_id, env_vars):
        if not self.token: return
        for key, val in env_vars.items():
            requests.put(f'{self.API}/v1/projects/{project_id}/env',
                headers=self._headers(),
                json={key: val})

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'glitch-{int(time.time())}-{i}'
            try:
                proj = self.remix_project(TEMPLATE_DOMAIN)
                if not proj:
                    print(f'[glitch] remix failed {i}'); continue
                pid    = proj.get('id')
                domain = proj.get('domain', f'gitmine-{i}')
                self.set_env(pid, {'RIG_ID': rig, 'POOL_REPO': pool_repo,
                                   'DEPLOY_KEY': os.environ.get('HARVEST_DEPLOY_KEY', '')})
                workers.append({'id': rig, 'algo': 'auto', 'hashrate': '~25KH/s',
                    'expires_at': 'never',
                    'url': f'https://{domain}.glitch.me'})
                print(f'[glitch] remixed -> {domain}.glitch.me')
            except Exception as e:
                print(f'[glitch] error: {e}')
            time.sleep(5)
        return workers
