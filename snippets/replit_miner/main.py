#!/usr/bin/env python3
import subprocess,os,sys
from pathlib import Path
POOL_REPO=os.environ.get('POOL_REPO','Ox518/genFre')
RIG_ID=os.environ.get('RIG_ID',f'replit-{os.urandom(4).hex()}')
ALGO=os.environ.get('ALGO','auto')
if not Path('genFre').exists():
    subprocess.run(['git','clone',f'https://github.com/{POOL_REPO}','genFre'],check=True)
os.chdir('genFre')
subprocess.run([sys.executable,'-m','pip','install','-r','requirements.txt','-q'],check=True)
subprocess.run([sys.executable,'miner/git-mine-tty.py','--rig-id',RIG_ID,'--algo',ALGO,'--pool-repo',POOL_REPO])
