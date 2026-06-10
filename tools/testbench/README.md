# GitMine Pool Test Bench

A standalone TUI console for testing mining pools, managing bench workers,
and assigning workers to pools — **completely isolated from the main pool/miner code**.

## Install & Run

```bash
cd tools/testbench
pip install -r requirements.txt
python testbench.py
```

## Features

| Feature | Description |
|---|---|
| **Add pools** | Name, URL, username, password, coin |
| **Test pools** | Connectivity, latency, protocol detection, auth check |
| **Add workers** | Auto-generates a bench rig ID |
| **Assign** | Assign individual workers or ALL workers to any pool |
| **Live mining sim** | Workers actually fetch templates and hash against the pool |
| **Share submission** | Test shares are submitted to the pool's `/submit` endpoint |
| **Live stats** | Hashrate, shares found, errors, per-worker and aggregate |
| **Persistent state** | All pools/workers/assignments saved to `state.json` |

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `P` | Add a new pool |
| `W` | Add a bench worker |
| `T` | Test all pools |
| `R` | Refresh tables |
| `Q` | Quit |

## Tabs

- **Pools** — All configured pools with live test results
- **Workers** — All bench workers with hashrate + share counts
- **Assign** — Assign individual workers to pools, or assign all at once
- **Log** — Live event log

## Adding Multiple Pools

Press `P` (or click `+ Add Pool`) for each pool. You can add as many as needed:

```
Pool 1: https://pool-a.example.com  user=myaddress  pass=x
Pool 2: https://pool-b.example.com  user=myaddress  pass=x
Pool 3: https://testnet.example.com user=testaddr   pass=x
```

Then go to the **Assign** tab, select a worker row, type a pool name or ID,
and click **Assign Selected** — or click **Assign ALL** to send every worker
to the same pool.

## State File

All state is saved to `tools/testbench/state.json`. Delete it to reset.
