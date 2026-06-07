# GitMine TTY

> A Git-native Trinity (TTY) mining pool. GitHub Actions is the pool operator. Git commits are shares. GitHub Pages is the dashboard. Zero servers.

## Architecture

```
Miners → git push shares → GitHub Actions validates → stats committed → GitHub Pages dashboard updates
```

## Stack

| Component | Technology | Cost |
|-----------|-----------|------|
| Pool Operator | GitHub Actions | Free |
| Dashboard | GitHub Pages (PWA) | Free |
| Real-time | Cloudflare Worker | Free |
| Auth | GitHub OAuth + WebAuthn | Free |
| Config/State | Git branches | Free |
| Miner Fleet | git-mine-tty daemon | Your power |

## Quick Start

### 1. Pool Operator Setup
```bash
git clone git@github.com:5mil/gitmine-tty.git
cd gitmine-tty
# Edit config/pool.yaml — add your TTY address, fee, payout threshold
vim config/pool.yaml
git add config/pool.yaml && git commit -m "config: set pool address" && git push
```

Add these GitHub Secrets:
- `POOL_ADDRESS` — your Trinity payout address
- `WORKER_SECRET` — secret for Cloudflare Worker webhook
- `TTY_RPC_USER` / `TTY_RPC_PASS` — Trinity daemon RPC credentials

### 2. Register a Miner Rig
```bash
# On your mining rig
git clone git@github.com:5mil/gitmine-tty.git
cd gitmine-tty

# Generate deploy key for this rig
ssh-keygen -t ed25519 -f fleet/rig-001/deploy-key -N ""
cat fleet/rig-001/deploy-key.pub  # Add this to repo Deploy Keys (read/write)

# Configure the rig
cp fleet/rig-example/config.yaml fleet/rig-001/config.yaml
vim fleet/rig-001/config.yaml
git add fleet/rig-001/ && git commit -m "fleet: register rig-001" && git push
```

### 3. Start Mining
```bash
# On the rig
pip install -r requirements.txt
RIG_ID=rig-001 DEPLOY_KEY=$(base64 -w0 fleet/rig-001/deploy-key) \
  python miner/git-mine-tty.py --address TYourTrinityAddress...
```

### 4. Deploy Cloudflare Worker (Real-time)
```bash
cd workers/gitmine-bridge
npm install
wrangler deploy
# Copy Worker URL → GitHub repo webhook → push events
```

## Algorithms

Trinity TTY supports three PoW algorithms. The pool rotates them per block:

| Algorithm | Target Hardware | Difficulty |
|-----------|----------------|------------|
| SHA256d | ASIC / GPU | 500,000 |
| Scrypt | GPU / ASIC | 12,000 |
| Myr-Groestl | GPU / CPU | 8,000 |

## Share Protocol

Miners push shares as signed git commits to `shares-pending` branch:
```
SHARE{"algo":"scrypt","nonce":"a1b2c3d4","hash":"f00d...","difficulty":12500,"miner":"TAddr..."}
```

GitHub Actions validates each share against the current template and moves commits to `shares-accepted` or `shares-rejected`.

## Fleet Config as Code (GitOps)

Each rig's config lives in `fleet/<rig-id>/config.yaml`. The miner daemon `git pull`s this file every loop — hot-reload with no restart required.

## Payouts

Payouts are multisig-style commit chains:
1. Action computes payout → commits tx hex to `payouts/pending/`
2. Pool operator signs via WebAuthn in PWA or `gitmine` TUI → push to `payouts/signed/`
3. Action broadcasts signed tx via public RPC → tags txid in `payouts/broadcast/`

## License

MIT
