#!/usr/bin/env python3
import os, base64, time
from pathlib import Path

CLOUD_INIT = """#cloud-config
packages: [git, python3-pip, python3-venv]
runcmd:
  - git clone https://github.com/Ox518/genFre /opt/gitmine
  - cd /opt/gitmine && python3 -m venv venv
  - /opt/gitmine/venv/bin/pip install -r requirements.txt -q
  - echo 'RIG_ID={rig_id}' >> /opt/gitmine/.env
  - echo 'DEPLOY_KEY={deploy_key}' >> /opt/gitmine/.env
  - echo 'POOL_REPO=Ox518/genFre' >> /opt/gitmine/.env
  - cp /opt/gitmine/deploy/gitmine.service /etc/systemd/system/
  - systemctl daemon-reload && systemctl enable gitmine && systemctl start gitmine
"""

class OracleCloudFreeEnroller:
    def gen_key(self, rig_id):
        try:
            from nacl.signing import SigningKey
            sk = SigningKey.generate()
            return base64.b64encode(bytes(sk)).decode(), sk.verify_key.encode().hex()
        except ImportError:
            return 'PLACEHOLDER','PLACEHOLDER'
    def enroll(self, count, platform, secrets=None):
        workers = []
        try: import oci
        except ImportError: print('[oracle] oci not installed'); return workers
        try:
            cfg = oci.config.from_file()
            compute = oci.core.ComputeClient(cfg)
        except Exception as e: print(f'[oracle] config: {e}'); return workers
        for i in range(count):
            rig_id = f'oracle-{i}-{int(time.time())}'
            priv, pub = self.gen_key(rig_id)
            ud = base64.b64encode(CLOUD_INIT.format(rig_id=rig_id,deploy_key=priv).encode()).decode()
            try:
                resp = compute.launch_instance(oci.core.models.LaunchInstanceDetails(
                    availability_domain='AD-1',compartment_id=cfg['tenancy'],
                    display_name=f'gitmine-{rig_id}',shape='VM.Standard.A1.Flex',
                    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=4,memory_in_gbs=24),
                    metadata={'user_data':ud}))
                Path(f'fleet/{rig_id}').mkdir(parents=True,exist_ok=True)
                Path(f'fleet/{rig_id}/deploy-key.pub').write_text(pub)
                workers.append({'id':rig_id,'algo':'scrypt','hashrate':'~220KH/s',
                    'expires_at':'never','url':f'https://cloud.oracle.com/compute/instances/{resp.data.id}'})
            except Exception as e: print(f'[oracle] launch failed: {e}')
        return workers
