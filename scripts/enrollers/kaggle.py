#!/usr/bin/env python3
import time, os, json
from datetime import datetime, timedelta
from pathlib import Path

class KaggleEnroller:
    def enroll(self, count, platform, secrets=None):
        workers = []
        try: import kaggle
        except ImportError: print('[kaggle] not installed'); return workers
        for i in range(count):
            slug = f'gitmine-harvest-{int(time.time())}-{i}'
            meta = {'id':f"{os.environ.get('KAGGLE_USERNAME','user')}/{slug}",
                'title':f'GitMine Harvest {i}','code_file':'snippets/kaggle_miner.ipynb',
                'language':'python','kernel_type':'notebook',
                'is_private':True,'enable_gpu':True,'enable_internet':True}
            mp = Path(f'/tmp/km_{i}.json')
            mp.write_text(json.dumps(meta))
            try:
                kaggle.api.kernel_push(mp.parent)
                workers.append({'id':f'kaggle-{slug}','algo':'sha256d','hashrate':'~250KH/s',
                    'expires_at':(datetime.utcnow()+timedelta(hours=12)).isoformat()+'Z',
                    'url':f'https://kaggle.com/code/{slug}'})
            except Exception as e: print(f'[kaggle] failed: {e}')
            time.sleep(5)
        return workers
