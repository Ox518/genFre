#!/usr/bin/env python3
"""
Supabase Edge Functions Zero-Auth Enroller
Free tier: 500K edge function invocations/month, 2 projects.
Deploys via Supabase Management API.
"""
import requests, time, os

EDGE_FN = """
import {{ serve }} from 'https://deno.land/std@0.168.0/http/server.ts';
const RIG  = Deno.env.get('RIG_ID')   ?? 'supabase-unknown';
const POOL = Deno.env.get('POOL_REPO') ?? 'Ox518/genFre';
serve(async (req) => {{
  await fetch(`https://raw.githubusercontent.com/${{POOL}}/main/fleet/harvest/workers.yaml`).catch(()=>{{}});
  return new Response(`GitMine Harvest | ${{RIG}}`, {{ status: 200 }});
}});
"""

class SupabaseEdgeEnroller:
    API = 'https://api.supabase.com/v1'

    def __init__(self):
        self.token = os.environ.get('SUPABASE_ACCESS_TOKEN', '')

    def enroll(self, count, platform, secrets=None):
        workers = []
        if not self.token:
            print('[supabase] SUPABASE_ACCESS_TOKEN not set — skipping')
            return workers
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        for i in range(count):
            proj_name = f'gitmine-{int(time.time())}-{i}'
            rig       = f'supabase-{proj_name}'
            try:
                # create project
                r = requests.post(f'{self.API}/projects', headers=headers, json={
                    'name': proj_name, 'db_pass': os.urandom(12).hex(),
                    'region': 'us-east-1', 'plan': 'free'})
                if r.status_code not in (200, 201): continue
                proj_ref = r.json()['ref']
                time.sleep(15)  # wait for project init
                # deploy edge function
                r2 = requests.post(
                    f'{self.API}/projects/{proj_ref}/functions',
                    headers=headers,
                    json={'slug': 'harvest', 'name': 'harvest',
                          'body': EDGE_FN,
                          'verify_jwt': False})
                if r2.status_code in (200, 201):
                    url = f'https://{proj_ref}.supabase.co/functions/v1/harvest'
                    workers.append({'id': rig, 'algo': 'lightweight', 'hashrate': '~1KH/s',
                        'expires_at': 'never', 'url': url})
                    print(f'[supabase] deployed {rig} -> {url}')
            except Exception as e:
                print(f'[supabase] error: {e}')
            time.sleep(5)
        return workers
