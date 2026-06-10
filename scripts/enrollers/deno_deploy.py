#!/usr/bin/env python3
"""
Deno Deploy Zero-Auth Enroller
Free tier: 100K req/day, 1M req/month, no credit card.
Deploys via Deno Deploy REST API or deployctl CLI.
"""
import requests, time, os, subprocess, shutil, json
from pathlib import Path

DENO_SCRIPT = """
const RIG  = Deno.env.get('RIG_ID')  ?? 'deno-unknown';
const POOL = Deno.env.get('POOL_REPO') ?? 'Ox518/genFre';

Deno.serve(async (req: Request) => {{
  const url = new URL(req.url);
  if (url.pathname === '/hb') {{
    // heartbeat
    await fetch(`https://raw.githubusercontent.com/${{POOL}}/main/fleet/harvest/workers.yaml`).catch(()=>{{}});
    return new Response(JSON.stringify({{rig: RIG, ts: Date.now()}}), 
      {{headers: {{'content-type':'application/json'}}}});
  }}
  return new Response(`GitMine Harvest | ${{RIG}}`);
}});
"""

class DenoDeployEnroller:
    API = 'https://api.deno.com/v1'

    def __init__(self):
        self.token = os.environ.get('DENO_DEPLOY_TOKEN', '')

    def deploy_via_api(self, name, rig, pool_repo):
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        # create project
        r = requests.post(f'{self.API}/projects', headers=headers, json={'name': name})
        if r.status_code not in (200, 201): return None
        project_id = r.json().get('id')
        # deploy
        script = DENO_SCRIPT.format()
        r2 = requests.post(f'{self.API}/projects/{project_id}/deployments', headers=headers,
            json={
                'entryPointUrl': 'main.ts',
                'assets': {'main.ts': {'kind': 'file', 'content': script, 'encoding': 'utf-8'}},
                'envVars': {'RIG_ID': rig, 'POOL_REPO': pool_repo},
                'includeBuildStep': False
            })
        if r2.status_code in (200, 201):
            domains = r2.json().get('domains', [])
            return f'https://{domains[0]}' if domains else f'https://{name}.deno.dev'
        return None

    def deploy_via_deployctl(self, name, rig, pool_repo):
        if not shutil.which('deployctl'): return None
        d = Path(f'/tmp/deno_{name}')
        d.mkdir(parents=True, exist_ok=True)
        (d / 'main.ts').write_text(DENO_SCRIPT)
        env = {**os.environ, 'RIG_ID': rig, 'POOL_REPO': pool_repo}
        if self.token: env['DENO_DEPLOY_TOKEN'] = self.token
        try:
            result = subprocess.run(
                ['deployctl', 'deploy', '--project', name, 'main.ts'],
                cwd=d, env=env, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return f'https://{name}.deno.dev'
        except Exception as e:
            print(f'[deno] deployctl failed: {e}')
        return None

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            name = f'gitmine-harvest-{int(time.time())}-{i}'
            rig  = f'deno-{name}'
            url  = None
            if self.token:
                url = self.deploy_via_api(name, rig, pool_repo)
            if not url:
                url = self.deploy_via_deployctl(name, rig, pool_repo)
            if url:
                workers.append({'id': rig, 'algo': 'lightweight', 'hashrate': '~1KH/s',
                    'expires_at': 'never', 'url': url})
                print(f'[deno] deployed {rig} -> {url}')
            else:
                print(f'[deno] skipped {name} — no token or CLI')
            time.sleep(3)
        return workers
