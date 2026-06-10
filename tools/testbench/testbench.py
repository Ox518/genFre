#!/usr/bin/env python3
"""
GitMine Pool Test Bench
Standalone TUI console for testing pools, managing workers, and
assigning miners across multiple pools — completely isolated from
the main pool code.

Usage:
    python tools/testbench/testbench.py

Requires:
    pip install rich textual requests pyyaml
"""
import json, time, threading, hashlib, struct, sys, os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import requests
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Button, Input, Label, DataTable,
    Static, Log, TabbedContent, TabPane, Select, Switch
)
from textual.reactive import reactive
from textual import work
from rich.text import Text
from rich.table import Table

# ─────────────────── State

STATE_FILE = Path('tools/testbench/state.json')

class State:
    def __init__(self):
        self.pools:   list[dict] = []   # {id, name, url, user, password, coin, algo, active}
        self.workers: list[dict] = []   # {id, rig_id, pool_id, status, hashrate, shares, errors}
        self.assignments: dict   = {}   # worker_id -> pool_id  (None = unassigned)
        self.load()

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            'pools':       self.pools,
            'workers':     self.workers,
            'assignments': self.assignments
        }, indent=2))

    def load(self):
        if STATE_FILE.exists():
            try:
                d = json.loads(STATE_FILE.read_text())
                self.pools       = d.get('pools', [])
                self.workers     = d.get('workers', [])
                self.assignments = d.get('assignments', {})
            except Exception:
                pass

    def add_pool(self, name, url, user, password, coin='FNNC', algo='auto') -> dict:
        pool = {'id': f'pool-{int(time.time())}-{len(self.pools)}',
                'name': name, 'url': url.rstrip('/'),
                'user': user, 'password': password,
                'coin': coin, 'algo': algo,
                'active': True, 'added': datetime.utcnow().isoformat()+'Z',
                'test_result': None}
        self.pools.append(pool)
        self.save()
        return pool

    def remove_pool(self, pool_id):
        self.pools = [p for p in self.pools if p['id'] != pool_id]
        self.assignments = {w: p for w, p in self.assignments.items() if p != pool_id}
        self.save()

    def add_worker(self, rig_id, pool_id=None) -> dict:
        w = {'id': f'worker-{int(time.time())}-{len(self.workers)}',
             'rig_id': rig_id, 'status': 'idle',
             'hashrate': 0.0, 'shares': 0, 'errors': 0,
             'added': datetime.utcnow().isoformat()+'Z'}
        self.workers.append(w)
        if pool_id:
            self.assignments[w['id']] = pool_id
        self.save()
        return w

    def assign(self, worker_id, pool_id):
        self.assignments[worker_id] = pool_id
        self.save()

    def assign_all(self, pool_id):
        for w in self.workers:
            self.assignments[w['id']] = pool_id
        self.save()

    def get_pool(self, pool_id):
        return next((p for p in self.pools if p['id'] == pool_id), None)

    def get_worker(self, worker_id):
        return next((w for w in self.workers if w['id'] == worker_id), None)

state = State()


# ─────────────────── Pool Tester (isolated from main miner code)

class PoolTester:
    """Tests a pool by:
    1. Fetching /template.json (GitMine native)
    2. Attempting Stratum getwork if template fails
    3. Returning a detailed TestResult
    """
    def test(self, pool: dict, timeout=10) -> dict:
        result = {
            'pool_id':   pool['id'],
            'url':       pool['url'],
            'timestamp': datetime.utcnow().isoformat()+'Z',
            'reachable': False,
            'protocol':  None,
            'latency_ms': None,
            'template':  None,
            'coin':      None,
            'algo':      None,
            'height':    None,
            'difficulty': None,
            'auth_ok':   None,
            'errors':    []
        }
        # 1. Connectivity ping
        try:
            t0 = time.time()
            r  = requests.get(pool['url'], timeout=timeout)
            result['latency_ms'] = round((time.time()-t0)*1000, 1)
            result['reachable']  = True
        except Exception as e:
            result['errors'].append(f'Unreachable: {e}')
            return result

        # 2. GitMine native template
        try:
            t0 = time.time()
            r  = requests.get(f"{pool['url']}/template.json", timeout=timeout)
            if r.status_code == 200:
                tmpl = r.json()
                result['protocol']   = 'gitmine_native'
                result['template']   = tmpl
                result['coin']       = tmpl.get('coin')
                result['algo']       = tmpl.get('algo')
                result['height']     = tmpl.get('height')
                result['difficulty'] = tmpl.get('difficulty')
                result['latency_ms'] = round((time.time()-t0)*1000, 1)
        except Exception as e:
            result['errors'].append(f'Template fetch: {e}')

        # 3. Auth test (submit dummy worker registration)
        if pool.get('user'):
            try:
                auth_r = requests.post(
                    f"{pool['url']}/worker",
                    json={'user': pool['user'], 'password': pool.get('password',''),
                          'rig': 'testbench-probe', 'pubkey': '00'*32},
                    timeout=timeout)
                result['auth_ok'] = auth_r.status_code in (200, 201, 202)
            except Exception as e:
                result['errors'].append(f'Auth test: {e}')
                result['auth_ok'] = False

        return result


# ─────────────────── Bench Worker (simulated miner that targets a pool)

class BenchWorker:
    """Simulates a miner worker against a pool for testing throughput"""
    def __init__(self, worker: dict, pool: dict, on_update=None):
        self.worker    = worker
        self.pool      = pool
        self.on_update = on_update
        self._stop     = threading.Event()
        self._thread   = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        self.worker['status'] = 'connecting'
        self._emit()
        # Fetch template
        try:
            r = requests.get(f"{self.pool['url']}/template.json", timeout=10)
            if r.status_code != 200:
                self.worker['status'] = 'template_fail'
                self._emit()
                return
            tmpl = r.json()
        except Exception as e:
            self.worker['status'] = f'error: {e}'
            self.worker['errors'] += 1
            self._emit()
            return

        self.worker['status'] = 'mining'
        blob   = bytes.fromhex(tmpl.get('blob', '00'*76))
        target = int(tmpl.get('target', 'f'*64), 16)
        algo   = tmpl.get('algo', 'sha256d')
        nonce  = 0
        start  = time.time()
        batch  = 5000

        while not self._stop.is_set():
            for _ in range(batch):
                h   = hashlib.sha256(hashlib.sha256(
                          blob[:76] + struct.pack('<I', nonce & 0xFFFFFFFF)
                      ).digest()).digest()
                val = int.from_bytes(h[::-1], 'big')
                if val <= target:
                    self.worker['shares'] += 1
                    self._submit_share(tmpl, nonce, h)
                nonce += 1
            elapsed = time.time() - start
            self.worker['hashrate'] = round(nonce / elapsed, 1)
            self._emit()

    def _submit_share(self, tmpl, nonce, h):
        share = {
            'coin':       tmpl.get('coin','TEST'),
            'algo':       tmpl.get('algo','sha256d'),
            'nonce':      struct.pack('<I', nonce & 0xFFFFFFFF).hex(),
            'hash':       h.hex(),
            'height':     tmpl.get('height',0),
            'difficulty': tmpl.get('difficulty',1),
            'miner':      self.pool.get('user','testbench'),
            'rig':        self.worker['rig_id'],
            'ts':         int(time.time())
        }
        try:
            r = requests.post(f"{self.pool['url']}/submit",
                json={'share': share, 'sig': '00'*64},
                timeout=5)
            if r.status_code not in (200,201,202):
                self.worker['errors'] += 1
        except Exception:
            self.worker['errors'] += 1

    def _emit(self):
        state.save()
        if self.on_update:
            self.on_update(self.worker)


# ─────────────────── TUI

class AddPoolModal(Container):
    DEFAULT_CSS = """
    AddPoolModal {
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        height: auto;
        width: 70;
        margin: 2 auto;
    }
    AddPoolModal Label { margin-bottom: 0; color: $text-muted; }
    AddPoolModal Input { margin-bottom: 1; }
    AddPoolModal .row { height: auto; }
    """
    def compose(self) -> ComposeResult:
        yield Label('Pool Name')
        yield Input(placeholder='My Test Pool', id='add_name')
        yield Label('Pool URL')
        yield Input(placeholder='https://pool.example.com', id='add_url')
        yield Label('Username / Address')
        yield Input(placeholder='your-wallet-address', id='add_user')
        yield Label('Password')
        yield Input(placeholder='x', password=True, id='add_pass')
        yield Label('Coin')
        yield Input(placeholder='FNNC', id='add_coin', value='FNNC')
        with Horizontal(classes='row'):
            yield Button('Add Pool', variant='primary', id='btn_add_pool')
            yield Button('Cancel', variant='default', id='btn_cancel_pool')


class TestBenchApp(App):
    CSS = """
    Screen {
        background: $background;
    }
    #sidebar {
        width: 28;
        background: $surface;
        border-right: solid $primary;
        padding: 1;
    }
    #sidebar Label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    #main {
        width: 1fr;
    }
    .stat-box {
        background: $surface;
        border: solid $primary;
        padding: 0 1;
        height: 3;
        content-align: center middle;
        text-align: center;
    }
    .stat-row {
        height: 3;
        margin-bottom: 1;
    }
    DataTable {
        height: 1fr;
    }
    #log_box {
        height: 14;
        background: $surface;
        border: solid $primary;
        margin-top: 1;
    }
    .action-row {
        height: 3;
        margin: 1 0;
    }
    .tag-ok    { color: green; }
    .tag-fail  { color: red; }
    .tag-warn  { color: yellow; }
    AddPoolModal { layer: overlay; }
    """

    BINDINGS = [
        Binding('q', 'quit', 'Quit'),
        Binding('p', 'add_pool', 'Add Pool'),
        Binding('w', 'add_worker', 'Add Worker'),
        Binding('t', 'test_all', 'Test All Pools'),
        Binding('r', 'refresh_ui', 'Refresh'),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id='sidebar'):
                yield Label('POOLS')
                yield Button('+ Add Pool',   variant='primary',   id='open_add_pool')
                yield Button('Test All',     variant='default',   id='btn_test_all')
                yield Label('WORKERS')
                yield Button('+ Add Worker', variant='success',   id='open_add_worker')
                yield Button('Assign All →', variant='warning',   id='btn_assign_all')
                yield Button('Start All',    variant='success',   id='btn_start_all')
                yield Button('Stop All',     variant='error',     id='btn_stop_all')
                yield Label('STATS')
                yield Static(id='sidebar_stats')
            with Vertical(id='main'):
                with TabbedContent():
                    with TabPane('Pools', id='tab_pools'):
                        yield DataTable(id='pool_table')
                    with TabPane('Workers', id='tab_workers'):
                        yield DataTable(id='worker_table')
                    with TabPane('Assign', id='tab_assign'):
                        yield DataTable(id='assign_table')
                        with Horizontal(classes='action-row'):
                            yield Button('Assign Selected → Pool', variant='primary', id='btn_assign_one')
                            yield Input(placeholder='Pool ID or Name', id='assign_pool_input')
                        yield Button('Assign ALL workers to pool ↑', variant='warning', id='btn_assign_all_2')
                    with TabPane('Log', id='tab_log'):
                        yield Log(id='bench_log', max_lines=500)
        yield Footer()
        # Modal (hidden by default)
        modal = AddPoolModal(id='add_pool_modal')
        modal.display = False
        yield modal

    def on_mount(self):
        self._workers_running: dict = {}  # worker_id -> BenchWorker
        self._setup_tables()
        self._refresh_all()
        self.set_interval(3, self._refresh_all)

    def _setup_tables(self):
        pt = self.query_one('#pool_table', DataTable)
        pt.add_columns('Name', 'URL', 'Coin', 'User', 'Reachable', 'Protocol', 'Height', 'Latency', 'Auth', 'ID')

        wt = self.query_one('#worker_table', DataTable)
        wt.add_columns('Rig ID', 'Status', 'Pool', 'Hashrate', 'Shares', 'Errors', 'ID')

        at = self.query_one('#assign_table', DataTable)
        at.add_columns('Worker', 'Current Pool', 'Status', 'Worker ID')

    def _refresh_all(self):
        self._refresh_pool_table()
        self._refresh_worker_table()
        self._refresh_assign_table()
        self._refresh_sidebar_stats()

    def _refresh_pool_table(self):
        pt = self.query_one('#pool_table', DataTable)
        pt.clear()
        for p in state.pools:
            tr = p.get('test_result') or {}
            reachable = ('✓', 'tag-ok') if tr.get('reachable') else ('✗', 'tag-fail') if tr else ('-', '')
            auth      = ('✓', 'tag-ok') if tr.get('auth_ok') else ('✗', 'tag-fail') if tr.get('auth_ok') is False else ('-', '')
            pt.add_row(
                p['name'],
                p['url'][:35]+'…' if len(p['url'])>35 else p['url'],
                p.get('coin','?'),
                p.get('user','')[:20],
                Text(reachable[0], style=reachable[1]),
                tr.get('protocol') or '-',
                str(tr.get('height') or '-'),
                f"{tr.get('latency_ms','-')}ms" if tr.get('latency_ms') else '-',
                Text(auth[0], style=auth[1]),
                p['id']
            )

    def _refresh_worker_table(self):
        wt = self.query_one('#worker_table', DataTable)
        wt.clear()
        for w in state.workers:
            pid  = state.assignments.get(w['id'])
            pool = state.get_pool(pid) if pid else None
            wt.add_row(
                w['rig_id'],
                w.get('status','idle'),
                pool['name'] if pool else Text('unassigned', style='yellow'),
                f"{w.get('hashrate',0):.0f} H/s",
                str(w.get('shares',0)),
                str(w.get('errors',0)),
                w['id']
            )

    def _refresh_assign_table(self):
        at = self.query_one('#assign_table', DataTable)
        at.clear()
        for w in state.workers:
            pid  = state.assignments.get(w['id'])
            pool = state.get_pool(pid) if pid else None
            at.add_row(
                w['rig_id'],
                pool['name'] if pool else Text('— unassigned —', style='yellow'),
                w.get('status','idle'),
                w['id']
            )

    def _refresh_sidebar_stats(self):
        total_hr  = sum(w.get('hashrate',0) for w in state.workers)
        total_sh  = sum(w.get('shares',0)   for w in state.workers)
        total_err = sum(w.get('errors',0)   for w in state.workers)
        mining    = sum(1 for w in state.workers if w.get('status')=='mining')
        self.query_one('#sidebar_stats', Static).update(
            f'Pools   : {len(state.pools)}\n'
            f'Workers : {len(state.workers)}\n'
            f'Mining  : {mining}\n'
            f'Hashrate: {total_hr:.0f} H/s\n'
            f'Shares  : {total_sh}\n'
            f'Errors  : {total_err}'
        )

    def _log(self, msg, level='INFO'):
        ts  = datetime.now().strftime('%H:%M:%S')
        log = self.query_one('#bench_log', Log)
        log.write_line(f'[{ts}] [{level}] {msg}')

    # ── Buttons

    def on_button_pressed(self, event: Button.Pressed):
        bid = event.button.id
        if bid == 'open_add_pool':    self._show_add_pool()
        elif bid == 'btn_cancel_pool': self._hide_add_pool()
        elif bid == 'btn_add_pool':   self._submit_add_pool()
        elif bid == 'btn_test_all':   self.action_test_all()
        elif bid == 'open_add_worker': self._quick_add_worker()
        elif bid in ('btn_assign_all', 'btn_assign_all_2'): self._assign_all_dialog()
        elif bid == 'btn_start_all':  self._start_all_workers()
        elif bid == 'btn_stop_all':   self._stop_all_workers()
        elif bid == 'btn_assign_one': self._assign_selected()

    def _show_add_pool(self):
        self.query_one('#add_pool_modal').display = True

    def _hide_add_pool(self):
        self.query_one('#add_pool_modal').display = False

    def _submit_add_pool(self):
        name = self.query_one('#add_name', Input).value.strip()
        url  = self.query_one('#add_url',  Input).value.strip()
        user = self.query_one('#add_user', Input).value.strip()
        pw   = self.query_one('#add_pass', Input).value.strip()
        coin = self.query_one('#add_coin', Input).value.strip() or 'FNNC'
        if not url:
            self._log('URL is required', 'ERROR'); return
        pool = state.add_pool(name or url, url, user, pw, coin)
        self._log(f'Added pool: {pool["name"]} ({pool["url"]})')
        self._hide_add_pool()
        self._refresh_all()
        self._test_pool(pool)

    def _quick_add_worker(self):
        import random, string
        rig_id = 'bench-' + ''.join(random.choices(string.ascii_lowercase+string.digits, k=6))
        pool_id = state.pools[0]['id'] if state.pools else None
        w = state.add_worker(rig_id, pool_id)
        self._log(f'Added worker: {w["rig_id"]}')
        self._refresh_all()

    def _assign_all_dialog(self):
        if not state.pools:
            self._log('No pools configured', 'WARN'); return
        # Assign all workers to first active pool
        p = next((p for p in state.pools if p.get('active')), state.pools[0])
        state.assign_all(p['id'])
        self._log(f'Assigned ALL workers to pool: {p["name"]}')
        self._refresh_all()

    def _assign_selected(self):
        at = self.query_one('#assign_table', DataTable)
        inp = self.query_one('#assign_pool_input', Input).value.strip()
        if not inp: self._log('Enter a Pool ID or Name', 'WARN'); return
        pool = next((p for p in state.pools if p['id']==inp or p['name'].lower()==inp.lower()), None)
        if not pool: self._log(f'Pool not found: {inp}', 'ERROR'); return
        row = at.cursor_row
        if row >= len(state.workers): return
        w = state.workers[row]
        state.assign(w['id'], pool['id'])
        self._log(f'Assigned {w["rig_id"]} -> {pool["name"]}')
        self._refresh_all()

    @work(thread=True)
    def _test_pool(self, pool: dict):
        self._log(f'Testing pool: {pool["name"]} ...')
        result = PoolTester().test(pool)
        pool['test_result'] = result
        state.save()
        if result['reachable']:
            self._log(f'✓ {pool["name"]} reachable | latency={result["latency_ms"]}ms | '
                      f'protocol={result["protocol"]} | height={result["height"]}', 'OK')
        else:
            self._log(f'✗ {pool["name"]} unreachable: {result["errors"]}', 'FAIL')
        self.call_from_thread(self._refresh_all)

    def action_test_all(self):
        for p in state.pools:
            self._test_pool(p)

    def _start_all_workers(self):
        for w in state.workers:
            if w['id'] in self._workers_running: continue
            pid  = state.assignments.get(w['id'])
            pool = state.get_pool(pid) if pid else None
            if not pool:
                self._log(f'{w["rig_id"]}: no pool assigned', 'WARN'); continue
            bw = BenchWorker(w, pool, on_update=lambda _: None)
            bw.start()
            self._workers_running[w['id']] = bw
            self._log(f'Started {w["rig_id"]} -> {pool["name"]}')

    def _stop_all_workers(self):
        for wid, bw in self._workers_running.items():
            bw.stop()
            w = state.get_worker(wid)
            if w: w['status'] = 'stopped'
        self._workers_running.clear()
        state.save()
        self._log('All workers stopped.')

    def action_add_pool(self):   self._show_add_pool()
    def action_add_worker(self): self._quick_add_worker()
    def action_refresh_ui(self): self._refresh_all()


if __name__ == '__main__':
    TestBenchApp().run()
