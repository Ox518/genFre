#!/usr/bin/env python3
"""
GitMine Pool Test Bench — Tkinter GUI
Standalone desktop GUI for testing pools, managing workers,
and assigning miners across multiple pools.

Usage:
    python tools/testbench/gui.py

Requires only stdlib (tkinter) + requests:
    pip install requests
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading, json, time, hashlib, struct, os, random, string
from pathlib import Path
from datetime import datetime
import requests

# ─────────────────────────────────────────── Colours / Theme
BG        = '#0f1117'
BG2       = '#1a1d27'
BG3       = '#252836'
ACCENT    = '#7c5cbf'
ACCENT2   = '#5e9bdc'
GREEN     = '#3ddc84'
RED       = '#ff5c5c'
YELLOW    = '#f5c542'
FG        = '#e8e8f0'
FG2       = '#9090a8'
FONT      = ('Consolas', 10)
FONT_B    = ('Consolas', 10, 'bold')
FONT_LG   = ('Consolas', 13, 'bold')
FONT_SM   = ('Consolas', 9)

# ─────────────────────────────────────────── State
STATE_FILE = Path('tools/testbench/state.json')

class State:
    def __init__(self):
        self.pools       = []
        self.workers     = []
        self.assignments = {}
        self.load()

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(
            {'pools': self.pools, 'workers': self.workers, 'assignments': self.assignments},
            indent=2))

    def load(self):
        if STATE_FILE.exists():
            try:
                d = json.loads(STATE_FILE.read_text())
                self.pools       = d.get('pools', [])
                self.workers     = d.get('workers', [])
                self.assignments = d.get('assignments', {})
            except Exception: pass

    def add_pool(self, name, url, user, password, coin='FNNC') -> dict:
        p = {'id': f'pool-{int(time.time())}-{len(self.pools)}',
             'name': name, 'url': url.rstrip('/'),
             'user': user, 'password': password,
             'coin': coin, 'active': True,
             'added': datetime.utcnow().isoformat()+'Z',
             'test_result': None}
        self.pools.append(p)
        self.save()
        return p

    def remove_pool(self, pool_id):
        self.pools       = [p for p in self.pools if p['id'] != pool_id]
        self.assignments = {w: p for w, p in self.assignments.items() if p != pool_id}
        self.save()

    def add_worker(self, rig_id, pool_id=None) -> dict:
        w = {'id': f'w-{int(time.time())}-{len(self.workers)}',
             'rig_id': rig_id, 'status': 'idle',
             'hashrate': 0.0, 'shares': 0, 'errors': 0,
             'added': datetime.utcnow().isoformat()+'Z'}
        self.workers.append(w)
        if pool_id:
            self.assignments[w['id']] = pool_id
        self.save()
        return w

    def remove_worker(self, worker_id):
        self.workers = [w for w in self.workers if w['id'] != worker_id]
        self.assignments.pop(worker_id, None)
        self.save()

    def assign(self, worker_id, pool_id):
        self.assignments[worker_id] = pool_id
        self.save()

    def assign_all(self, pool_id):
        for w in self.workers:
            self.assignments[w['id']] = pool_id
        self.save()

    def get_pool(self, pid):   return next((p for p in self.pools   if p['id']==pid), None)
    def get_worker(self, wid): return next((w for w in self.workers if w['id']==wid), None)


state = State()


# ─────────────────────────────────────────── Pool Tester
class PoolTester:
    def test(self, pool, timeout=10):
        res = {'reachable': False, 'protocol': None, 'latency_ms': None,
               'coin': None, 'algo': None, 'height': None,
               'difficulty': None, 'auth_ok': None, 'errors': []}
        try:
            t0 = time.time()
            requests.get(pool['url'], timeout=timeout)
            res['latency_ms'] = round((time.time()-t0)*1000, 1)
            res['reachable']  = True
        except Exception as e:
            res['errors'].append(str(e)[:80])
            return res
        try:
            r = requests.get(f"{pool['url']}/template.json", timeout=timeout)
            if r.status_code == 200:
                t = r.json()
                res['protocol']   = 'gitmine'
                res['coin']       = t.get('coin')
                res['algo']       = t.get('algo')
                res['height']     = t.get('height')
                res['difficulty'] = t.get('difficulty')
        except Exception as e:
            res['errors'].append(f'template: {e}'[:60])
        if pool.get('user'):
            try:
                r2 = requests.post(f"{pool['url']}/worker",
                    json={'user': pool['user'], 'password': pool.get('password',''),
                          'rig': 'gui-probe', 'pubkey': '00'*32},
                    timeout=timeout)
                res['auth_ok'] = r2.status_code in (200,201,202)
            except Exception:
                res['auth_ok'] = False
        return res


# ─────────────────────────────────────────── Bench Worker
class BenchWorker:
    def __init__(self, worker, pool, log_fn=None):
        self.worker  = worker
        self.pool    = pool
        self.log_fn  = log_fn
        self._stop   = threading.Event()

    def start(self):
        self._stop.clear()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()
        self.worker['status'] = 'stopped'
        state.save()

    def _run(self):
        self.worker['status'] = 'connecting'
        try:
            r = requests.get(f"{self.pool['url']}/template.json", timeout=10)
            if r.status_code != 200:
                self.worker['status'] = 'no_template'
                state.save(); return
            tmpl = r.json()
        except Exception as e:
            self.worker['status'] = f'err:{str(e)[:20]}'
            self.worker['errors'] += 1
            state.save(); return

        blob   = bytes.fromhex(tmpl.get('blob','00'*76))
        target = int(tmpl.get('target','f'*64), 16)
        nonce  = 0
        start  = time.time()
        self.worker['status'] = 'mining'
        while not self._stop.is_set():
            for _ in range(8000):
                h   = hashlib.sha256(hashlib.sha256(
                          blob[:76]+struct.pack('<I', nonce&0xFFFFFFFF)
                      ).digest()).digest()
                if int.from_bytes(h[::-1],'big') <= target:
                    self.worker['shares'] += 1
                    try:
                        requests.post(f"{self.pool['url']}/submit",
                            json={'share':{'nonce': struct.pack('<I',nonce&0xFFFFFFFF).hex(),
                                           'hash': h.hex(), 'rig': self.worker['rig_id'],
                                           'miner': self.pool.get('user','bench')},
                                  'sig':'00'*64}, timeout=5)
                    except Exception:
                        self.worker['errors'] += 1
                nonce += 1
            elapsed = max(time.time()-start, 0.001)
            self.worker['hashrate'] = round(nonce/elapsed, 1)
            state.save()


# ─────────────────────────────────────────── Dialogs
class AddPoolDialog(tk.Toplevel):
    def __init__(self, parent, on_save):
        super().__init__(parent)
        self.on_save  = on_save
        self.result   = None
        self.title('Add Pool')
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self.wait_window()

    def _build(self):
        pad = dict(padx=12, pady=4, sticky='ew')
        fields = [
            ('Pool Name',     'name',     '',       False),
            ('Pool URL',      'url',      'https://', False),
            ('Username/Addr', 'user',     '',       False),
            ('Password',      'password', 'x',      True),
            ('Coin',          'coin',     'FNNC',   False),
        ]
        self._vars = {}
        for i, (label, key, default, secret) in enumerate(fields):
            tk.Label(self, text=label, bg=BG, fg=FG2, font=FONT).grid(row=i, column=0, **pad)
            v = tk.StringVar(value=default)
            self._vars[key] = v
            show = '*' if secret else ''
            e = tk.Entry(self, textvariable=v, bg=BG3, fg=FG, font=FONT,
                         insertbackground=FG, relief='flat', width=38, show=show)
            e.grid(row=i, column=1, **pad)

        fr = tk.Frame(self, bg=BG)
        fr.grid(row=len(fields), column=0, columnspan=2, pady=10)
        tk.Button(fr, text='Add Pool', bg=ACCENT, fg=FG, font=FONT_B,
                  relief='flat', padx=14, command=self._save).pack(side='left', padx=6)
        tk.Button(fr, text='Cancel', bg=BG3, fg=FG2, font=FONT,
                  relief='flat', padx=14, command=self.destroy).pack(side='left', padx=6)

    def _save(self):
        url = self._vars['url'].get().strip()
        if not url:
            messagebox.showerror('Error','URL is required', parent=self); return
        self.on_save(
            self._vars['name'].get().strip() or url,
            url,
            self._vars['user'].get().strip(),
            self._vars['password'].get().strip(),
            self._vars['coin'].get().strip() or 'FNNC'
        )
        self.destroy()


class AddWorkerDialog(tk.Toplevel):
    def __init__(self, parent, pools, on_save):
        super().__init__(parent)
        self.on_save = on_save
        self.title('Add Worker')
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._pools = pools
        self._build()
        self.wait_window()

    def _build(self):
        pad = dict(padx=12, pady=6, sticky='ew')
        tk.Label(self, text='Rig ID', bg=BG, fg=FG2, font=FONT).grid(row=0, column=0, **pad)
        self._rig = tk.StringVar(value='bench-'+''.join(random.choices(string.ascii_lowercase+string.digits,k=5)))
        tk.Entry(self, textvariable=self._rig, bg=BG3, fg=FG, font=FONT,
                 insertbackground=FG, relief='flat', width=30).grid(row=0, column=1, **pad)

        tk.Label(self, text='Count', bg=BG, fg=FG2, font=FONT).grid(row=1, column=0, **pad)
        self._count = tk.IntVar(value=1)
        tk.Spinbox(self, from_=1, to=50, textvariable=self._count,
                   bg=BG3, fg=FG, font=FONT, relief='flat', width=10).grid(row=1, column=1, **pad)

        tk.Label(self, text='Assign to Pool', bg=BG, fg=FG2, font=FONT).grid(row=2, column=0, **pad)
        pool_names = ['(unassigned)'] + [p['name'] for p in self._pools]
        self._pool_var = tk.StringVar(value=pool_names[0] if len(pool_names)==1 else pool_names[1])
        ttk.Combobox(self, textvariable=self._pool_var, values=pool_names,
                     font=FONT, state='readonly', width=28).grid(row=2, column=1, **pad)

        fr = tk.Frame(self, bg=BG)
        fr.grid(row=3, column=0, columnspan=2, pady=10)
        tk.Button(fr, text='Add Worker(s)', bg=GREEN, fg='#000', font=FONT_B,
                  relief='flat', padx=14, command=self._save).pack(side='left', padx=6)
        tk.Button(fr, text='Cancel', bg=BG3, fg=FG2, font=FONT,
                  relief='flat', padx=14, command=self.destroy).pack(side='left', padx=6)

    def _save(self):
        count = self._count.get()
        pname = self._pool_var.get()
        pool  = next((p for p in self._pools if p['name']==pname), None)
        base  = self._rig.get().strip() or 'bench'
        for i in range(count):
            rig_id = f'{base}-{i:02d}' if count > 1 else base
            self.on_save(rig_id, pool['id'] if pool else None)
        self.destroy()


# ─────────────────────────────────────────── Main GUI
class TestBenchGUI:
    def __init__(self, root):
        self.root    = root
        self.root.title('GitMine Pool Test Bench')
        self.root.configure(bg=BG)
        self.root.geometry('1200x750')
        self.root.minsize(900, 600)
        self._running: dict = {}   # worker_id -> BenchWorker
        self._build()
        self._refresh()
        self.root.after(3000, self._auto_refresh)

    # ── Layout
    def _build(self):
        self._build_topbar()
        paned = tk.PanedWindow(self.root, orient='horizontal',
                               bg=BG, sashwidth=5, sashrelief='flat')
        paned.pack(fill='both', expand=True, padx=8, pady=(0,8))
        left  = tk.Frame(paned, bg=BG2, width=260)
        right = tk.Frame(paned, bg=BG)
        paned.add(left,  minsize=200)
        paned.add(right, minsize=500)
        self._build_sidebar(left)
        self._build_notebook(right)
        self._build_statusbar()

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=BG3, height=44)
        bar.pack(fill='x', padx=0, pady=0)
        bar.pack_propagate(False)
        tk.Label(bar, text=' ⛏  GitMine Test Bench', bg=BG3, fg=ACCENT,
                 font=FONT_LG).pack(side='left', padx=16)
        for text, cmd, col in [
            ('+ Pool',    self._open_add_pool,   ACCENT),
            ('+ Worker',  self._open_add_worker, GREEN),
            ('Test All',  self._test_all,        ACCENT2),
            ('Start All', self._start_all,       GREEN),
            ('Stop All',  self._stop_all,        RED),
        ]:
            tk.Button(bar, text=text, bg=col, fg='#000' if col in (GREEN,) else FG,
                      font=FONT_B, relief='flat', padx=10,
                      command=cmd).pack(side='left', padx=4, pady=8)

    def _build_sidebar(self, parent):
        parent.pack_propagate(False)
        tk.Label(parent, text='STATS', bg=BG2, fg=FG2, font=FONT_B).pack(anchor='w', padx=12, pady=(12,2))
        self._stats_frame = tk.Frame(parent, bg=BG2)
        self._stats_frame.pack(fill='x', padx=8)
        self._stat_labels = {}
        for key, label in [('pools','Pools'), ('workers','Workers'),
                            ('mining','Mining'), ('hashrate','Hashrate'),
                            ('shares','Shares'), ('errors','Errors')]:
            row = tk.Frame(self._stats_frame, bg=BG2)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=f'{label}:', bg=BG2, fg=FG2, font=FONT_SM, width=10, anchor='w').pack(side='left')
            lbl = tk.Label(row, text='-', bg=BG2, fg=FG, font=FONT_B, anchor='w')
            lbl.pack(side='left')
            self._stat_labels[key] = lbl

        ttk.Separator(parent, orient='horizontal').pack(fill='x', padx=8, pady=10)
        tk.Label(parent, text='POOLS', bg=BG2, fg=FG2, font=FONT_B).pack(anchor='w', padx=12, pady=(0,4))
        self._pool_list_frame = tk.Frame(parent, bg=BG2)
        self._pool_list_frame.pack(fill='both', expand=True, padx=8)

    def _build_notebook(self, parent):
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook',       background=BG,  borderwidth=0)
        style.configure('TNotebook.Tab',   background=BG3, foreground=FG2,
                        font=FONT_B, padding=[14,6])
        style.map('TNotebook.Tab',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', FG)])
        style.configure('Treeview',        background=BG2, foreground=FG,
                        fieldbackground=BG2, font=FONT, rowheight=22)
        style.configure('Treeview.Heading', background=BG3, foreground=ACCENT2,
                        font=FONT_B)
        style.map('Treeview', background=[('selected', ACCENT)])

        nb = ttk.Notebook(parent)
        nb.pack(fill='both', expand=True)
        self.nb = nb

        # Pools tab
        pools_tab = tk.Frame(nb, bg=BG)
        nb.add(pools_tab, text=' Pools ')
        self._build_pool_table(pools_tab)

        # Workers tab
        workers_tab = tk.Frame(nb, bg=BG)
        nb.add(workers_tab, text=' Workers ')
        self._build_worker_table(workers_tab)

        # Assign tab
        assign_tab = tk.Frame(nb, bg=BG)
        nb.add(assign_tab, text=' Assign ')
        self._build_assign_tab(assign_tab)

        # Log tab
        log_tab = tk.Frame(nb, bg=BG)
        nb.add(log_tab, text=' Log ')
        self._build_log_tab(log_tab)

    def _tree(self, parent, cols):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill='both', expand=True, padx=6, pady=6)
        vsb = ttk.Scrollbar(frame, orient='vertical')
        hsb = ttk.Scrollbar(frame, orient='horizontal')
        tree = ttk.Treeview(frame, columns=cols, show='headings',
                            yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        return tree

    def _build_pool_table(self, parent):
        cols = ('name','url','coin','user','ok','proto','height','latency','auth','id')
        t = self._tree(parent, cols)
        heads = [('Name',8),('URL',28),('Coin',5),('User',14),('Up',3),
                 ('Protocol',10),('Height',7),('Latency',8),('Auth',4),('ID',24)]
        for col, (h, w) in zip(cols, heads):
            t.heading(col, text=h)
            t.column(col, width=w*9, anchor='w', stretch=False)
        t.column('url', width=240, stretch=True)
        self._pool_tree = t
        # right-click menu
        m = tk.Menu(self.root, tearoff=0, bg=BG3, fg=FG, font=FONT)
        m.add_command(label='Test Pool',   command=self._test_selected_pool)
        m.add_command(label='Remove Pool', command=self._remove_selected_pool)
        t.bind('<Button-3>', lambda e: (t.identify_row(e.y) and m.tk_popup(e.x_root, e.y_root)))

    def _build_worker_table(self, parent):
        cols = ('rig','status','pool','hashrate','shares','errors','id')
        t = self._tree(parent, cols)
        for col, (h, w) in zip(cols, [('Rig ID',14),('Status',10),('Pool',14),
                                       ('H/s',10),('Shares',7),('Errors',6),('ID',20)]):
            t.heading(col, text=h)
            t.column(col, width=w*9, anchor='w', stretch=False)
        t.column('rig', stretch=True)
        self._worker_tree = t
        m = tk.Menu(self.root, tearoff=0, bg=BG3, fg=FG, font=FONT)
        m.add_command(label='Start Worker',  command=self._start_selected_worker)
        m.add_command(label='Stop Worker',   command=self._stop_selected_worker)
        m.add_command(label='Remove Worker', command=self._remove_selected_worker)
        t.bind('<Button-3>', lambda e: (t.identify_row(e.y) and m.tk_popup(e.x_root, e.y_root)))

    def _build_assign_tab(self, parent):
        top = tk.Frame(parent, bg=BG)
        top.pack(fill='x', padx=8, pady=6)

        # Pool selector
        tk.Label(top, text='Target Pool:', bg=BG, fg=FG2, font=FONT).pack(side='left', padx=(0,6))
        self._assign_pool_var = tk.StringVar()
        self._assign_pool_cb  = ttk.Combobox(top, textvariable=self._assign_pool_var,
                                              font=FONT, state='readonly', width=28)
        self._assign_pool_cb.pack(side='left', padx=4)

        tk.Button(top, text='Assign Selected', bg=ACCENT, fg=FG, font=FONT_B,
                  relief='flat', padx=10,
                  command=self._assign_selected).pack(side='left', padx=8)
        tk.Button(top, text='Assign ALL →', bg=YELLOW, fg='#000', font=FONT_B,
                  relief='flat', padx=10,
                  command=self._assign_all_to_selected).pack(side='left', padx=4)

        # Assign table
        cols = ('rig','current_pool','status','wid')
        t = self._tree(parent, cols)
        for col, (h, w) in zip(cols,[('Rig ID',16),('Current Pool',18),('Status',10),('Worker ID',20)]):
            t.heading(col, text=h)
            t.column(col, width=w*9, anchor='w', stretch=False)
        t.column('rig', stretch=True)
        self._assign_tree = t

    def _build_log_tab(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill='both', expand=True, padx=6, pady=6)
        vsb = ttk.Scrollbar(frame)
        vsb.pack(side='right', fill='y')
        self._log_text = tk.Text(frame, bg=BG2, fg=FG, font=FONT_SM,
                                  insertbackground=FG, relief='flat',
                                  yscrollcommand=vsb.set, state='disabled')
        self._log_text.pack(fill='both', expand=True)
        vsb.config(command=self._log_text.yview)
        self._log_text.tag_config('ok',   foreground=GREEN)
        self._log_text.tag_config('err',  foreground=RED)
        self._log_text.tag_config('warn', foreground=YELLOW)
        self._log_text.tag_config('info', foreground=ACCENT2)
        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.pack(fill='x', padx=6, pady=(0,4))
        tk.Button(btn_frame, text='Clear Log', bg=BG3, fg=FG2, font=FONT_SM,
                  relief='flat', padx=8, command=self._clear_log).pack(side='right')

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG3, height=24)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)
        self._status_var = tk.StringVar(value='Ready')
        tk.Label(bar, textvariable=self._status_var, bg=BG3, fg=FG2,
                 font=FONT_SM, anchor='w').pack(side='left', padx=10)
        self._clock_var = tk.StringVar()
        tk.Label(bar, textvariable=self._clock_var, bg=BG3, fg=FG2,
                 font=FONT_SM, anchor='e').pack(side='right', padx=10)
        self._tick_clock()

    def _tick_clock(self):
        self._clock_var.set(datetime.now().strftime('%Y-%m-%d  %H:%M:%S'))
        self.root.after(1000, self._tick_clock)

    # ── Refresh
    def _refresh(self):
        self._refresh_pool_tree()
        self._refresh_worker_tree()
        self._refresh_assign_tree()
        self._refresh_sidebar()
        self._refresh_pool_list()
        self._refresh_assign_pool_combo()

    def _auto_refresh(self):
        self._refresh()
        self.root.after(3000, self._auto_refresh)

    def _refresh_pool_tree(self):
        t = self._pool_tree
        t.delete(*t.get_children())
        for p in state.pools:
            tr = p.get('test_result') or {}
            ok   = '✓' if tr.get('reachable') else ('✗' if tr else '—')
            auth = '✓' if tr.get('auth_ok') else ('✗' if tr.get('auth_ok') is False else '—')
            iid = t.insert('', 'end', values=(
                p['name'],
                p['url'],
                p.get('coin','?'),
                p.get('user','')[:18],
                ok,
                tr.get('protocol') or '—',
                tr.get('height') or '—',
                f"{tr.get('latency_ms','—')}ms" if tr.get('latency_ms') else '—',
                auth,
                p['id']
            ))
            if tr.get('reachable'):  t.item(iid, tags=('ok',))
            elif tr:                 t.item(iid, tags=('fail',))
        t.tag_configure('ok',   foreground=GREEN)
        t.tag_configure('fail', foreground=RED)

    def _refresh_worker_tree(self):
        t = self._worker_tree
        t.delete(*t.get_children())
        for w in state.workers:
            pid  = state.assignments.get(w['id'])
            pool = state.get_pool(pid) if pid else None
            status = w.get('status','idle')
            iid = t.insert('', 'end', values=(
                w['rig_id'],
                status,
                pool['name'] if pool else '— unassigned —',
                f"{w.get('hashrate',0):.0f} H/s",
                w.get('shares',0),
                w.get('errors',0),
                w['id']
            ))
            tag = 'mining' if status=='mining' else 'idle' if status=='idle' else 'warn'
            t.item(iid, tags=(tag,))
        t.tag_configure('mining', foreground=GREEN)
        t.tag_configure('idle',   foreground=FG2)
        t.tag_configure('warn',   foreground=YELLOW)

    def _refresh_assign_tree(self):
        t = self._assign_tree
        t.delete(*t.get_children())
        for w in state.workers:
            pid  = state.assignments.get(w['id'])
            pool = state.get_pool(pid) if pid else None
            t.insert('', 'end', values=(
                w['rig_id'],
                pool['name'] if pool else '— unassigned —',
                w.get('status','idle'),
                w['id']
            ))

    def _refresh_sidebar(self):
        total_hr  = sum(w.get('hashrate',0) for w in state.workers)
        total_sh  = sum(w.get('shares',0)   for w in state.workers)
        total_err = sum(w.get('errors',0)   for w in state.workers)
        mining    = sum(1 for w in state.workers if w.get('status')=='mining')
        self._stat_labels['pools'].config(text=str(len(state.pools)))
        self._stat_labels['workers'].config(text=str(len(state.workers)))
        self._stat_labels['mining'].config(text=str(mining), fg=GREEN if mining else FG)
        self._stat_labels['hashrate'].config(text=f'{total_hr:,.0f} H/s', fg=GREEN if total_hr>0 else FG)
        self._stat_labels['shares'].config(text=str(total_sh))
        self._stat_labels['errors'].config(text=str(total_err), fg=RED if total_err else FG)

    def _refresh_pool_list(self):
        for w in self._pool_list_frame.winfo_children():
            w.destroy()
        for p in state.pools:
            tr  = p.get('test_result') or {}
            dot = '●'
            col = GREEN if tr.get('reachable') else (RED if tr else FG2)
            row = tk.Frame(self._pool_list_frame, bg=BG2)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=dot, bg=BG2, fg=col, font=FONT).pack(side='left')
            tk.Label(row, text=p['name'][:22], bg=BG2, fg=FG, font=FONT_SM,
                     anchor='w').pack(side='left', padx=4)

    def _refresh_assign_pool_combo(self):
        names = [p['name'] for p in state.pools]
        self._assign_pool_cb['values'] = names
        if names and not self._assign_pool_var.get():
            self._assign_pool_var.set(names[0])

    # ── Logging
    def _log(self, msg, level='info'):
        ts  = datetime.now().strftime('%H:%M:%S')
        txt = self._log_text
        txt.config(state='normal')
        txt.insert('end', f'[{ts}] ', 'info')
        txt.insert('end', msg+'\n', level)
        txt.see('end')
        txt.config(state='disabled')
        self._status_var.set(msg[:100])

    def _clear_log(self):
        self._log_text.config(state='normal')
        self._log_text.delete('1.0','end')
        self._log_text.config(state='disabled')

    # ── Pool actions
    def _open_add_pool(self):
        def save(name, url, user, pw, coin):
            p = state.add_pool(name, url, user, pw, coin)
            self._log(f'Added pool: {p["name"]} ({p["url"]})')
            self._refresh()
            threading.Thread(target=self._run_test, args=(p,), daemon=True).start()
        AddPoolDialog(self.root, save)

    def _run_test(self, pool):
        self._log(f'Testing {pool["name"]} ...')
        res = PoolTester().test(pool)
        pool['test_result'] = res
        state.save()
        if res['reachable']:
            self._log(f'✓ {pool["name"]} up | {res["latency_ms"]}ms | '
                      f'proto={res["protocol"]} | h={res["height"]}', 'ok')
        else:
            self._log(f'✗ {pool["name"]} unreachable — {res["errors"]}', 'err')
        self._refresh()

    def _test_all(self):
        for p in state.pools:
            threading.Thread(target=self._run_test, args=(p,), daemon=True).start()

    def _test_selected_pool(self):
        sel = self._pool_tree.selection()
        if not sel: return
        pid  = self._pool_tree.item(sel[0])['values'][-1]
        pool = state.get_pool(str(pid))
        if pool:
            threading.Thread(target=self._run_test, args=(pool,), daemon=True).start()

    def _remove_selected_pool(self):
        sel = self._pool_tree.selection()
        if not sel: return
        pid = str(self._pool_tree.item(sel[0])['values'][-1])
        if messagebox.askyesno('Remove', 'Remove this pool?', parent=self.root):
            state.remove_pool(pid)
            self._log(f'Removed pool {pid}', 'warn')
            self._refresh()

    # ── Worker actions
    def _open_add_worker(self):
        def save(rig_id, pool_id):
            w = state.add_worker(rig_id, pool_id)
            self._log(f'Added worker: {w["rig_id"]}')
            self._refresh()
        AddWorkerDialog(self.root, state.pools, save)

    def _start_worker(self, w):
        if w['id'] in self._running: return
        pid  = state.assignments.get(w['id'])
        pool = state.get_pool(pid) if pid else None
        if not pool:
            self._log(f'{w["rig_id"]}: no pool assigned', 'warn'); return
        bw = BenchWorker(w, pool, log_fn=self._log)
        bw.start()
        self._running[w['id']] = bw
        self._log(f'Started {w["rig_id"]} → {pool["name"]}')

    def _stop_worker(self, w):
        bw = self._running.pop(w['id'], None)
        if bw: bw.stop()
        self._log(f'Stopped {w["rig_id"]}', 'warn')

    def _start_all(self):
        for w in state.workers: self._start_worker(w)

    def _stop_all(self):
        for w in list(state.workers): self._stop_worker(w)
        self._refresh()

    def _start_selected_worker(self):
        sel = self._worker_tree.selection()
        if not sel: return
        wid = str(self._worker_tree.item(sel[0])['values'][-1])
        w   = state.get_worker(wid)
        if w: self._start_worker(w)

    def _stop_selected_worker(self):
        sel = self._worker_tree.selection()
        if not sel: return
        wid = str(self._worker_tree.item(sel[0])['values'][-1])
        w   = state.get_worker(wid)
        if w: self._stop_worker(w)

    def _remove_selected_worker(self):
        sel = self._worker_tree.selection()
        if not sel: return
        wid = str(self._worker_tree.item(sel[0])['values'][-1])
        w   = state.get_worker(wid)
        if not w: return
        self._stop_worker(w)
        state.remove_worker(wid)
        self._log(f'Removed worker {w["rig_id"]}', 'warn')
        self._refresh()

    # ── Assign actions
    def _assign_selected(self):
        sel   = self._assign_tree.selection()
        pname = self._assign_pool_var.get()
        if not sel or not pname: return
        pool  = next((p for p in state.pools if p['name']==pname), None)
        if not pool: self._log(f'Pool not found: {pname}', 'err'); return
        for item in sel:
            wid = str(self._assign_tree.item(item)['values'][-1])
            state.assign(wid, pool['id'])
            w = state.get_worker(wid)
            self._log(f'Assigned {w["rig_id"]} → {pool["name"]}')
        self._refresh()

    def _assign_all_to_selected(self):
        pname = self._assign_pool_var.get()
        if not pname: return
        pool  = next((p for p in state.pools if p['name']==pname), None)
        if not pool: self._log(f'Pool not found: {pname}', 'err'); return
        state.assign_all(pool['id'])
        self._log(f'Assigned ALL workers → {pool["name"]}')
        self._refresh()


# ─────────────────────────────────────────── Entry
if __name__ == '__main__':
    root = tk.Tk()
    app  = TestBenchGUI(root)
    root.mainloop()
