# GitMine Instruction Manual

GitMine is a Git-native dual-coin mining pool where GitHub Actions acts as the pool operator, Git commits can represent shares on the Git-native path, Supabase provides live state and realtime data, and GitHub Pages serves the dashboard.[cite:177]
This repository contains the pool server, miner client, fleet configuration, relay components, deployment files, dashboard assets, scripts, and the new test bench tools under `tools/testbench`.[cite:176]

## Repository Map

The repository root currently includes `.github`, `config`, `deploy`, `docs`, `fleet`, `miner`, `pool-server`, `relay`, `scripts`, `snippets`, `supabase`, and `tools`, plus the main `README.md`.[cite:176]
The miner client entrypoint is `miner/git-mine.py`, while the standalone pool test bench lives under `tools/testbench` and now includes both a Textual TUI and a Tkinter GUI.[cite:173][cite:175]

## System Overview

GitMine supports two coins: Fennec (`FNNC`) using YescryptR16 on RPC port 8339, and Trinity (`TTY`) using SHA256d on RPC port 12345.[cite:177]
The documented production path is miners to a Stratum TCP server at `pool.gitmine.io:3333`, then into Supabase for shares, workers, balances, and pool stats, with GitHub Pages serving the dashboard and GitHub Actions validating, updating stats, and handling payouts.[cite:177]
The documented stack includes GitHub Actions for pool operations, GitHub Pages for the dashboard PWA, Supabase for database and realtime, GitHub OAuth Device Flow for auth, optional self-hosted Fennec realtime bridge, Git branches for config/state, and common miner software like cgminer, sgminer, XMRig, and bfgminer.[cite:177]

## Main Interfaces

GitMine currently exposes three practical operator interfaces in this repository: the web dashboard documented in the root README, the standalone terminal test bench at `tools/testbench/testbench.py`, and the standalone desktop Tkinter GUI at `tools/testbench/gui.py`.[cite:177][cite:174][cite:175]
The dashboard is published at [5mil.github.io/gitmine-tty](https://5mil.github.io/gitmine-tty), the Textual TUI is started from `tools/testbench` with `python testbench.py`, and the Tkinter GUI is started from the same directory with `python gui.py`.[cite:177][cite:174][cite:175]

## Dashboard Manual

The documented user flow starts by signing in with GitHub on the dashboard, where the GitHub login becomes the pool identity without separate pool account creation.[cite:177]
After sign-in, the dashboard shows the miner command to use, including sample cgminer commands that point to `stratum+tcp://pool.gitmine.io:3333` and use `yourgithub.gitmine` as the username format.[cite:177]
The root README states the username format is `githublogin.workername`, such as `5mil.rig1` or `5mil.asic`, and it notes that live shares appear on the dashboard when the realtime Supabase connection is active.[cite:177]

### Example miner commands

```bash
# Fennec (YescryptR16 — CPU/GPU)
cgminer --url stratum+tcp://pool.gitmine.io:3333 \
  --user yourgithub.gitmine --pass x \
  --algorithm yescryptr16

# Trinity (SHA256d — ASIC/GPU)
cgminer --url stratum+tcp://pool.gitmine.io:3333 \
  --user yourgithub.gitmine --pass x \
  --algorithm sha256d
```

## Database Manual

The root documentation says five Supabase tables power the pool: `users`, `workers`, `shares`, `balances`, and `pool_stats`.[cite:177]
According to the README, `users` stores GitHub identity data, `workers` stores registered worker names and coin, `shares` stores accepted and rejected shares plus difficulty and algorithm data, `balances` stores miner payout balances per coin, and `pool_stats` stores snapshot metrics such as hashrate, shares, and block height.[cite:177]
The README also says writes come from the Actions workflow, reads use the anon key with RLS, and setup can be done by running `scripts/supabase_schema.sql` or allowing `scripts/update_stats.py` to auto-create tables on first run.[cite:177]

## Required Secrets

The documented GitHub Actions secrets are `FNNC_POOL_ADDRESS`, `FNNC_RPC_PASS`, `TTY_POOL_ADDRESS`, `TTY_RPC_PASS`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FENNEC_SECRET`, and `FENNEC_URL`.[cite:177]
The README describes these as payout addresses and RPC passwords for Fennec and Trinity, the Supabase project URL and service role key, plus optional relay bridge settings for Fennec.[cite:177]
Without those secrets, the documented pool operator workflow in `.github/workflows/pool.yml` cannot perform the full template, stats, payout, and broadcast cycle described in the README.[cite:177]

## Pool Operator Workflow

The root README says the pool workflow runs every 2 minutes and also on share pushes.[cite:177]
It documents seven main steps: fetch templates from Fennec and Trinity RPC, select the active template per algorithm, validate shares from `shares-pending`, update `pool_stats` in Supabase, process payouts into `payouts/pending/`, broadcast signed payouts via RPC, and deploy `docs/` to GitHub Pages.[cite:177]
This means the production pool path is GitHub-driven even when miners use Stratum, while the Git-native path uses commit messages on the `shares-pending` branch for share ingestion.[cite:177]

## Git-Native Miner Manual

The `miner/git-mine.py` script supports two startup modes: loading a config file with `--config`, or using direct flags such as `--coin`, `--address`, `--rig`, and `--pool`.[cite:173]
When no config file is provided, the script requires both `--coin` and `--address`, defaults the rig name to `rig-001`, defaults the pool URL to `https://5mil.github.io/gitmine-tty`, and defaults threads to 1.[cite:173]
When a config file is used, the script loads `coin`, `address`, `rig_id`, `pool`, `threads`, and a `private_key`, then reconstructs the Ed25519 signing key from PKCS8 hex.[cite:173]

### Basic manual-run examples

```bash
python miner/git-mine.py --coin FNNC --address FYourAddress --rig rig-001
python miner/git-mine.py --config ~/gitmine.json
```

## Miner Internals

The miner code maps `FNNC` to `yescryptr16` and `TTY` to `sha256d` through `ALGO_MAP`.[cite:173]
It fetches work from `pool_url.rstrip('/') + '/template.json'`, refreshes templates roughly every 25 seconds, and refuses to mine when the template coin does not match the requested coin.[cite:173]
For accepted candidate shares, it builds a share object containing the coin, algo, nonce, hash, height, difficulty, miner address, pubkey, rig, and timestamp, signs that payload with Ed25519, and submits it through a git commit and push to `shares-pending`.[cite:173]

## Share Submission Format

The root README documents the Git-native share format as a commit message beginning with `SHARE{...}|SIG{...}`.[cite:177]
The miner implementation constructs that commit message as `SHARE{json}|SIG{sig}` and pushes `HEAD:shares-pending` after creating an empty commit.[cite:173]
Together, those sources show that the Git-native miner path is commit-based and signature-verified rather than using only the Stratum share flow.[cite:177][cite:173]

## Key Management

When the miner is run without a provided config key, `miner/git-mine.py` generates an Ed25519 keypair on first run, stores the secret in `fleet/<rig_id>/keys/signing.key`, and prints the public key for registration on the dashboard.[cite:173]
The file path is created under the repository root, permissions are set to `0600`, and subsequent runs reuse the same key if the file already exists.[cite:173]
The script also supports importing a key from PKCS8 DER hex using `key_from_pkcs8_hex` for config-based setups.[cite:173]

## Difficulty Guidance

The root README documents four difficulty presets in the password field: `d=1` for auto or vardiff, `d=512` for mid-range GPUs, `d=8192` for high-end GPUs, and `d=65536` for TTY ASICs.[cite:177]
It explicitly says these presets are passed as the Stratum password, for example `--pass d=512`.[cite:177]
The algorithm table also states FNNC targets CPU and GPU hardware while TTY targets ASIC and GPU hardware.[cite:177]

## Optional Relay

The README documents an optional Fennec realtime bridge for sub-second dashboard updates without polling.[cite:177]
The documented startup command is `python fennec/bridge.py --config config/pool.yaml` after installing `websockets`, `aiohttp`, and `pyyaml`.[cite:177]
It also notes that GitHub webhooks can point to `http://<your-ip>:8766/webhook` or a systemd unit can be used via `fennec/gitmine-fennec.service`.[cite:177]

## Fleet Configuration

The README says each rig’s config lives in `fleet/<rig-id>/config.yaml`, and that rigs can hot-reload with `git pull` without a restart.[cite:177]
The example workflow in the README is to clone the repo, copy `fleet/rig-example/config.yaml` to `fleet/rig-001/config.yaml`, edit it, commit the new rig folder, and push it.[cite:177]
This is the GitOps layer for rig state alongside the live operator, miner, and dashboard components.[cite:177]

## Test Bench Overview

The test bench is isolated from the main pool code and lives under `tools/testbench`.[cite:174][cite:175]
The Textual TUI was added as `tools/testbench/testbench.py`, and the Tkinter desktop GUI was added as `tools/testbench/gui.py`.[cite:174][cite:175]
Both interfaces use the same `tools/testbench/state.json` file for persistence, as documented in the updated test bench README and visible in the GUI/TUI implementation notes already committed.[cite:174][cite:175]

## Tkinter GUI Manual

The Tkinter GUI is started with `cd tools/testbench`, `pip install requests`, and `python gui.py`.[cite:175]
The updated test bench README describes the GUI as a dark-themed desktop window with a top bar, sidebar stats, pool health indicators, tabs for Pools, Workers, Assign, and Log, right-click context menus, auto-refresh every 3 seconds, and persistent state in `state.json`.[cite:175]
The GUI top bar includes Add Pool, Add Worker, Test All, Start All, and Stop All actions, and the Assign tab supports selecting workers, choosing a target pool from a dropdown, and assigning selected workers or all workers at once.[cite:175]

### Tkinter GUI workflow

1. Start the GUI from `tools/testbench`.[cite:175]
2. Click **+ Pool** and enter a pool name, pool URL, username or address, password, and coin.[cite:175]
3. Add workers with **+ Worker**, choosing the rig ID, worker count, and optional default assigned pool.[cite:175]
4. Use **Test All** to probe pool connectivity and populate latency, protocol, and auth status in the Pools tab.[cite:175]
5. Use the **Assign** tab dropdown to route selected workers or all workers to a specific pool.[cite:175]
6. Start workers individually from the context menu or globally with **Start All**.[cite:175]

## Textual TUI Manual

The Textual TUI is started with `cd tools/testbench`, `pip install -r requirements.txt`, and `python testbench.py`.[cite:174]
Its README documents support for adding pools, testing pools, adding workers, assigning individual workers or all workers, running live mining simulation against real pool templates, submitting test shares to `/submit`, and persisting all pools, workers, and assignments in `state.json`.[cite:174]
The TUI binds keyboard shortcuts including `P` for Add Pool, `W` for Add Worker, `T` for Test All Pools, `R` for Refresh, and `Q` for Quit.[cite:174]

## Test Bench Protocol Behavior

The test bench pool tester checks reachability, requests `/template.json`, and attempts an auth-style probe by POSTing to `/worker` with `user`, `password`, `rig`, and `pubkey` fields.[cite:174][cite:175]
The simulated bench workers then fetch `template.json`, hash locally, and submit test shares to the pool’s `/submit` endpoint.[cite:174][cite:175]
That makes the bench suitable for isolated pool endpoint testing without involving the rest of the production pool workflow.[cite:174][cite:175]

## State File Manual

The shared test bench state file is `tools/testbench/state.json`.[cite:174][cite:175]
It stores `pools`, `workers`, and `assignments`, and both the TUI and GUI load and save that structure directly.[cite:174][cite:175]
Deleting that file resets the saved pool list, worker list, and all assignments for the test bench environment.[cite:174]

## Common Operating Procedures

### Add a single test pool

1. Open either the GUI or TUI test bench.[cite:174][cite:175]
2. Add a pool with the pool URL, username or payout address, password, and target coin.[cite:174][cite:175]
3. Run a pool test to confirm reachability and inspect `template.json` response details.[cite:174][cite:175]
4. Add one or more workers and assign them to that pool.[cite:174][cite:175]
5. Start the workers and watch hashrate, shares, errors, and auth or template failures in the interface.[cite:174][cite:175]

### Test multiple pools and distribute workers

1. Add each pool as a separate entry in the test bench.[cite:174][cite:175]
2. Add the workers you want to simulate.[cite:174][cite:175]
3. Assign all workers to one pool for a stress test, or assign workers individually to compare pool behavior side by side.[cite:174][cite:175]
4. Use the pools view to compare reachability, protocol, height, latency, and auth results while the workers view tracks per-worker stats.[cite:174][cite:175]

## Production vs Test Bench

The production system documented in the root README is centered on Stratum, Supabase, GitHub Actions, payouts, and GitHub Pages.[cite:177]
The test bench does not replace that full workflow; instead, it directly exercises test pool endpoints such as `/template.json`, `/worker`, and `/submit` without requiring the rest of the pool code to be involved.[cite:174][cite:175]
That separation is useful for validating pool endpoints, credentials, routing, and worker assignment logic before integrating with the broader operator path.[cite:174][cite:175]

## Troubleshooting

If the GUI or TUI shows a pool as unreachable, the first probe is a direct HTTP request to the pool base URL and then to `/template.json`, so failures there usually indicate the URL is wrong, the pool is down, or the endpoint shape does not match the expected GitMine-style test bench protocol.[cite:174][cite:175]
If workers remain unassigned or idle, the saved assignment in `state.json` may not point to a valid pool, or no pool may have been selected when the workers were created.[cite:174][cite:175]
If the Git-native miner fails to submit shares, the miner code shows the push step depends on successful local git commits and a push to `origin` on `HEAD:shares-pending`.[cite:173]

## Quick Reference

| Task | Command or Path |
|---|---|
| Dashboard | [5mil.github.io/gitmine-tty](https://5mil.github.io/gitmine-tty) [cite:177] |
| Git-native miner | `python miner/git-mine.py --coin FNNC --address FYourAddress --rig rig-001` [cite:173] |
| Config miner | `python miner/git-mine.py --config ~/gitmine.json` [cite:173] |
| Tkinter GUI | `cd tools/testbench && pip install requests && python gui.py` [cite:175] |
| Textual TUI | `cd tools/testbench && pip install -r requirements.txt && python testbench.py` [cite:174] |
| Test bench state | `tools/testbench/state.json` [cite:174][cite:175] |
| Miner source | `miner/git-mine.py` [cite:173] |
| Root guide | `README.md` [cite:177] |

## Links

- Root repository: [Ox518/genFre](https://github.com/Ox518/genFre) [cite:176]
- Tkinter GUI: [tools/testbench/gui.py](https://github.com/Ox518/genFre/blob/main/tools/testbench/gui.py) [cite:175]
- Textual TUI: [tools/testbench/testbench.py](https://github.com/Ox518/genFre/blob/main/tools/testbench/testbench.py) [cite:174]
- Miner client: [miner/git-mine.py](https://github.com/Ox518/genFre/blob/main/miner/git-mine.py) [cite:173]
- Main README: [README.md](https://github.com/Ox518/genFre/blob/main/README.md) [cite:177]
