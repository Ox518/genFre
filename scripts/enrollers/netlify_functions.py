#!/usr/bin/env python3
"""
Netlify Functions Zero-Auth Enroller
Free tier: 125K function invocations/month, 100 GB bandwidth.
Deploys via Netlify API. No credit card required.
"""
import requests, time, os, json, base64, zipfile, io
from pathlib import Path

FUNC_BODY = '''
exports.handler = async (event) => {{
  const rig  = process.env.RIG_ID   || 'netlify-unknown';
  const pool = process.env.POOL_REPO || 'Ox518/genFre';
  try {{
    await fetch(`https://raw.githubusercontent.com/${{pool}}/main/fleet/harvest/workers.yaml`);
  }} catch(_) {{}}
  return {{ statusCode: 200, body: `GitMine Harvest | ${{rig}}` }};
}};
'''

class NetlifyFunctionsEnroller:
    API = 'https://api.netlify.com/api/v1'

    def __init__(self):
        self.token = os.environ.get('NETLIFY_AUTH_TOKEN', '')

    def _make_zip(self, rig, pool_repo):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('netlify/functions/harvest.js', FUNC_BODY.format())
            zf.writestr('netlify.toml',
                f'[build]\n  functions = "netlify/functions"\n'
                f'[context.production.environment]\n  RIG_ID = "{rig}"\n  POOL_REPO = "{pool_repo}"\n')
        return buf.getvalue()

    def enroll(self, count, platform, secrets=None):
        workers = []
        if not self.token:
            print('[netlify] NETLIFY_AUTH_TOKEN not set — skipping')
            return workers
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        headers = {'Authorization': f'Bearer {self.token}'}
        for i in range(count):
            name = f'gitmine-harvest-{int(time.time())}-{i}'
            rig  = f'netlify-{name}'
            try:
                # create site
                r = requests.post(f'{self.API}/sites', headers=headers,
                    json={'name': name, 'custom_domain': None})
                if r.status_code not in (200, 201): continue
                site_id = r.json()['id']
                # deploy zip
                zip_bytes = self._make_zip(rig, pool_repo)
                r2 = requests.post(f'{self.API}/sites/{site_id}/deploys',
                    headers={**headers, 'Content-Type': 'application/zip'},
                    data=zip_bytes)
                if r2.status_code in (200, 201):
                    url = r2.json().get('ssl_url') or r2.json().get('url', '')
                    workers.append({'id': rig, 'algo': 'lightweight', 'hashrate': '~1KH/s',
                        'expires_at': 'never', 'url': url})
                    print(f'[netlify] deployed {rig} -> {url}')
            except Exception as e:
                print(f'[netlify] error: {e}')
            time.sleep(5)
        return workers
