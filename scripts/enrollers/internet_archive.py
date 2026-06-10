#!/usr/bin/env python3
"""
Internet Archive S3-Compatible Zero-Auth Uploader
The Internet Archive provides an S3-compatible API that accepts
UNAUTHENTICATED uploads for public items in some configurations.
More reliably: IA allows account-less item creation via their
simple upload endpoint for open-access content.
We use IA as a persistent config/state store — upload worker
manifests as publicly readable items that act as worker registration.
Free, permanent, no account required for basic uploads.
"""
import requests, time, os, json
from datetime import datetime

IA_BASE = 'https://s3.us.archive.org'

class InternetArchiveEnroller:
    def __init__(self):
        # IA S3 credentials — optional, anon uploads to open items work without
        self.access = os.environ.get('IA_ACCESS_KEY', '')
        self.secret = os.environ.get('IA_SECRET_KEY', '')

    def _headers(self, identifier, title):
        h = {
            'x-archive-meta-mediatype': 'data',
            'x-archive-meta-title':     title,
            'x-archive-meta-subject':   'gitmine;harvest;worker',
            'x-archive-auto-make-bucket': '1',
            'Content-Type': 'application/json'
        }
        if self.access and self.secret:
            h['Authorization'] = f'LOW {self.access}:{self.secret}'
        return h

    def upload_worker_manifest(self, rig_id, pool_repo):
        identifier = f'gitmine-harvest-{rig_id}-{int(time.time())}'
        title      = f'GitMine Harvest Worker {rig_id}'
        manifest   = json.dumps({
            'rig_id': rig_id, 'pool_repo': pool_repo,
            'enrolled': datetime.utcnow().isoformat() + 'Z',
            'algo': 'auto', 'status': 'active'
        }, indent=2).encode()
        url = f'{IA_BASE}/{identifier}/worker.json'
        headers = self._headers(identifier, title)
        try:
            r = requests.put(url, headers=headers, data=manifest, timeout=30)
            if r.status_code in (200, 201):
                return f'https://archive.org/details/{identifier}'
        except Exception as e:
            print(f'[ia] error: {e}')
        return None

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'ia-{int(time.time())}-{i}'
            url = self.upload_worker_manifest(rig, pool_repo)
            if url:
                workers.append({
                    'id': rig, 'algo': 'ia_store',
                    'hashrate': '~0KH/s', 'expires_at': 'never',
                    'url': url,
                    'note': 'Internet Archive dead-drop — permanent public state.'
                })
                print(f'[ia] uploaded manifest {rig} -> {url}')
            time.sleep(3)
        return workers
