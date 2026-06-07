# GitMine

> A Git-native dual-coin mining pool. GitHub Actions is the pool operator. Git commits are shares. GitHub Pages is the dashboard. Zero servers.

## Coins

| Coin | Ticker | Algorithm | RPC Port |
|------|--------|-----------|----------|
| Fennec | FNNC | YescryptR16 | 8339 |
| Trinity | TTY | SHA256d | 12345 |

## Architecture

```
Miners → git push shares → GitHub Actions validates → stats committed → GitHub Pages dashboard updates
```

## Stack

| Component | Technology | Cost |
|-----------|-----------|------|
| Pool Operator | GitHub Actions | Free |
| Dashboard | GitHub Pages (PWA) | Free |
| Real-time | Relay (self-hosted WS) | Free |
| Auth | GitHub OAuth + WebAuthn | Free |
| Config/State | Git branches | Free |
| Miner Fleet | git-mine daemon | Your power |

## Quick Start

### 1. Add GitHub Secrets

In repo Settings → Secrets and variables → Actions, add:

| Secret | Description |
|--------|-------------|
| `FNNC_POOL_ADDRESS` | Your Fennec payout address (starts with F) |
| `FNNC_RPC_PASS` | Fennec daemon RPC password |
| `TTY_POOL_ADDRESS` | Your Trinity payout address |
| `TTY_RPC_PASS` | Trinity daemon RPC password |
| `RELAY_SECRET` | Shared secret for Relay bridge (optional) |
| `RELAY_URL` | URL of your Relay bridge (optional) |

### 2. Register a Miner Rig

```bash
git clone git@github.com:5mil/gitmine-tty.git
cd gitmine-tty
ssh-keygen -t ed25519 -f fleet/rig-001/deploy-key -N ""
cat fleet/rig-001/deploy-key.pub  # Add to repo Deploy Keys (read/write)
cp fleet/rig-example/config.yaml fleet/rig-001/config.yaml
vim fleet/rig-001/config.yaml     # Set coin, algo, miner address
git add fleet/rig-001/ && git commit -m "fleet: register rig-001" && git push
```

### 3. Start Mining

```bash
pip install -r requirements.txt
# Mine Fennec (YescryptR16)
RIG_ID=rig-001 python miner/git-mine.py --coin FNNC --address FYourFennecAddress
# Mine Trinity (SHA256d)
RIG_ID=rig-001 python miner/git-mine.py --coin TTY --address TYourTrinityAddress
```

### 4. Deploy Relay (optional, for real-time dashboard)

```bash
pip install websockets aiohttp pyyaml
python relay/bridge.py --config config/pool.yaml
# Then configure GitHub webhook → http://<your-ip>:8766/webhook
```

## Share Protocol

Miners push shares as signed git commits to `shares-pending`:
```
SHARE{"coin":"FNNC","algo":"yescryptr16","nonce":"a1b2c3d4","hash":"f00d...","height":123456,"miner":"FAddr...","pubkey":"ed25519hex..."}
|SIG{ed25519signaturehex}
```

## Algorithms

| Coin | Algorithm | Difficulty | Target Hardware |
|------|-----------|------------|----------------|
| FNNC | YescryptR16 | 8,000 | CPU/GPU |
| TTY | SHA256d | 500,000 | ASIC/GPU |

## Payouts

1. Action computes payout → commits tx hex to `payouts/pending/`
2. Pool operator signs via WebAuthn in PWA → push to `payouts/signed/`
3. Action broadcasts signed tx via public RPC → tags txid in `payouts/broadcast/`

## Fleet Config (GitOps)

Each rig's config lives in `fleet/<rig-id>/config.yaml`. The miner daemon hot-reloads via `git pull` — no restart required.

## License

MIT
