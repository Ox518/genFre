# GitMine Pool Test Bench

Two interfaces — both read/write the same `state.json`:

| Interface | File | Requirements |
|---|---|---|
| **Tkinter GUI** (desktop) | `gui.py` | `pip install requests` (stdlib only) |
| **Textual TUI** (terminal) | `testbench.py` | `pip install rich textual requests` |

## Quick Start (GUI)

```bash
cd tools/testbench
pip install requests
python gui.py
```

## Quick Start (TUI)

```bash
cd tools/testbench
pip install rich textual requests
python testbench.py
```

## GUI Features

- Dark themed desktop window (1200x750, resizable)
- **Top bar** — Add Pool, Add Worker, Test All, Start All, Stop All
- **Sidebar** — live aggregate stats + coloured pool health dots
- **Pools tab** — all pools with reachability, protocol, height, latency, auth result
- **Workers tab** — all workers with status, assigned pool, H/s, shares, errors
- **Assign tab** — select workers, pick target pool from dropdown, assign individually or all at once
- **Log tab** — colour-coded event log (green=ok, red=err, yellow=warn)
- Right-click context menus on pool and worker rows
- Auto-refresh every 3 seconds
- All state persisted to `state.json`

## Adding Multiple Pools

Click **+ Pool** for each pool. Fields:
- Pool Name (label)
- Pool URL
- Username / Address
- Password
- Coin (default: FNNC)

## Assigning Workers

1. Go to **Assign** tab
2. Select one or more worker rows (Ctrl+click for multi)
3. Pick target pool from the dropdown
4. Click **Assign Selected** — or click **Assign ALL →** to route everything

## Running Bench Workers

- Right-click a worker → **Start Worker**
- Or click **Start All** in the top bar
- Workers fetch a real template from the pool and mine against it
- Test shares are submitted to `/submit`
- Click **Stop All** or right-click → **Stop Worker** to halt
