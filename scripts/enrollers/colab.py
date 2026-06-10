#!/usr/bin/env python3
import time
from datetime import datetime, timedelta

NOTEBOOK_URL = 'https://colab.research.google.com/github/Ox518/genFre/blob/main/snippets/colab_miner.ipynb'

class ColabEnroller:
    def enroll(self, count, platform, secrets=None):
        workers = []
        try: from playwright.sync_api import sync_playwright
        except ImportError: print('[colab] playwright not installed'); return workers
        with sync_playwright() as p:
            for i in range(count):
                try:
                    browser = p.chromium.launch(headless=True)
                    page    = browser.new_page()
                    page.goto(NOTEBOOK_URL, timeout=60000)
                    page.wait_for_timeout(5000)
                    try: page.click('[data-testid="connect-button"]',timeout=10000)
                    except: pass
                    page.wait_for_timeout(8000)
                    try: page.keyboard.press('Control+F9')
                    except: pass
                    url = page.url
                    browser.close()
                    workers.append({'id':f'colab-{i}-{int(time.time())}',
                        'algo':'sha256d','hashrate':'~180KH/s',
                        'expires_at':(datetime.utcnow()+timedelta(hours=12)).isoformat()+'Z','url':url})
                    time.sleep(10)
                except Exception as e: print(f'[colab] {i} failed: {e}')
        return workers
