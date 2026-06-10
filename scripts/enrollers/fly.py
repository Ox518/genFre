#!/usr/bin/env python3
import subprocess, time, os, shutil
from pathlib import Path

FLY_TOML = """
app = "{app}"
primary_region = "ord"
[build]
  dockerfile = "Dockerfile.miner"
[env]
  POOL_REPO = "Ox518/genFre"
  RIG_ID    = "{rig}"
  ALGO      = "scrypt"
[[services]]
  internal_port = 8080
  protocol = "tcp"
"""

class FlyIoEnroller:
    def enroll(self, count, platform, secrets=None):
        workers = []
        token = os.environ.get('FLY_API_TOKEN','')
        if not token: print('[fly] FLY_API_TOKEN not set'); return workers
        for i in range(count):
            app = f'gitmine-harvest-{int(time.time())}-{i}'
            rig = f'fly-{app}'
            d   = Path(f'/tmp/{app}')
            d.mkdir(parents=True,exist_ok=True)
            (d/'fly.toml').write_text(FLY_TOML.format(app=app,rig=rig))
            src = Path('snippets/fly_miner/Dockerfile.miner')
            if src.exists(): shutil.copy(src, d/'Dockerfile.miner')
            env = {**os.environ,'FLY_API_TOKEN':token}
            try:
                subprocess.run(['flyctl','launch','--no-deploy','--name',app,'--region','ord'],
                    cwd=d,env=env,check=True,capture_output=True)
                subprocess.run(['flyctl','deploy','--remote-only'],
                    cwd=d,env=env,check=True,capture_output=True)
                workers.append({'id':rig,'algo':'scrypt','hashrate':'~80KH/s',
                    'expires_at':'never','url':f'https://{app}.fly.dev'})
            except subprocess.CalledProcessError as e: print(f'[fly] failed: {e}')
            time.sleep(10)
        return workers
