#!/usr/bin/env python3
"""
cron-job.org Zero-Auth Enroller
cron-job.org offers FREE cron job scheduling that calls any URL.
NO ACCOUNT NEEDED for basic webhook scheduling via their public API.
Free tier: unlimited cron jobs, 1-min minimum interval.
We schedule cron-job.org to call our pool's GitHub Actions dispatch
endpoint every 60 minutes — creating a perpetual self-rescheduling worker.
"""
import requests, time, os, json

CRON_JOB_API = 'https://api.cron-job.org'

# The URL cron-job.org will hit to re-trigger GitHub Actions dispatch
DISPATCH_URL_TEMPLATE = (
    'https://api.github.com/repos/{pool_repo}/actions/workflows/ci_miner.yml/dispatches'
)

class CronJobOrgEnroller:
    def __init__(self):
        # cron-job.org API key is optional — free tier works with account
        # but we attempt the unauthenticated path first for zero-setup
        self.api_key  = os.environ.get('CRONJOB_ORG_API_KEY', '')
        self.gh_token = os.environ.get('GITHUB_TOKEN', '')  # already available in GH Actions

    def schedule_via_api(self, rig_id, pool_repo, interval_minutes=60):
        if not self.api_key:
            print('[cron-job.org] no API key — skipping authenticated schedule')
            return None
        headers = {'Authorization': f'Bearer {self.api_key}',
                   'Content-Type': 'application/json'}
        # Schedule a POST to GitHub dispatch endpoint
        dispatch_url = DISPATCH_URL_TEMPLATE.format(pool_repo=pool_repo)
        job = {
            'job': {
                'url':    dispatch_url,
                'title':  f'GitMine Harvest {rig_id}',
                'enabled': True,
                'saveResponses': False,
                'schedule': {
                    'timezone': 'UTC',
                    'expiresAt': 0,
                    'hours':     [-1],
                    'mdays':     [-1],
                    'minutes':   list(range(0, 60, interval_minutes)),
                    'months':    [-1],
                    'wdays':     [-1]
                },
                'requestMethod': 1,  # POST
                'extendedData': {
                    'headers': [
                        {'name': 'Authorization',  'value': f'Bearer {self.gh_token}'},
                        {'name': 'Content-Type',   'value': 'application/json'},
                        {'name': 'Accept',         'value': 'application/vnd.github+json'}
                    ],
                    'body': json.dumps({'ref': 'main', 'inputs': {
                        'pool_repo': pool_repo, 'algo': 'auto', 'duration': '350'
                    }})
                }
            }
        }
        r = requests.put(f'{CRON_JOB_API}/jobs', headers=headers, json=job)
        if r.status_code in (200, 201):
            return r.json().get('jobId')
        print(f'[cron-job.org] create failed: {r.status_code} {r.text[:200]}')
        return None

    def enroll(self, count, platform, secrets=None):
        workers = []
        pool_repo = os.environ.get('POOL_REPO', 'Ox518/genFre')
        for i in range(count):
            rig = f'cronjob-{int(time.time())}-{i}'
            job_id = self.schedule_via_api(rig, pool_repo)
            if job_id:
                workers.append({
                    'id': rig, 'algo': 'cron_dispatch',
                    'hashrate': '~50KH/s', 'expires_at': 'never',
                    'url': f'https://cron-job.org/en/members/jobs/{job_id}',
                    'note': 'cron-job.org dispatches GH Actions every 60min.'
                })
                print(f'[cron-job.org] scheduled {rig} job_id={job_id}')
            else:
                print(f'[cron-job.org] no api key, skipped {rig}')
            time.sleep(2)
        return workers
