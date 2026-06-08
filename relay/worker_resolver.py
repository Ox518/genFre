#!/usr/bin/env python3
"""
GitMine — Worker Resolver

When a miner connects to Stratum with username "githubusername.anything":
  1. Split on the first dot  →  prefix = "githubusername", suffix = "anything"
  2. Look up (or lazily create) the Supabase user + worker row
  3. Return worker metadata so the pool can track shares + credit balances

This module is imported by bridge.py and by the Stratum adapter.
It can also be called standalone as an HTTP micro-endpoint:

  python relay/worker_resolver.py
  # POST /resolve  {"worker_name": "alice.rig1", "coin": "FNNC"}
  # → {"ok": true, "user_id": "...", "worker_id": "...", ...}

Requirements:
  pip install aiohttp supabase
  env:  SUPABASE_URL, SUPABASE_SERVICE_KEY
"""

import os
import re
import asyncio
import logging
from typing import Optional

from aiohttp import web
from supabase import create_client, Client

log = logging.getLogger("resolver")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")  # service_role key

_sb: Optional[Client] = None

WORKER_RE = re.compile(r'^[a-zA-Z0-9_-]+\.[a-zA-Z0-9_.-]+$')


def supabase() -> Client:
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars")
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


def parse_worker_name(worker_name: str) -> tuple[str, str]:
    """Split 'alice.rig1' → ('alice', 'rig1'). Raises ValueError if invalid."""
    if not WORKER_RE.match(worker_name):
        raise ValueError(f"Invalid worker name: {worker_name!r}")
    prefix, _, suffix = worker_name.partition('.')
    return prefix, suffix


def resolve_worker(
    worker_name: str,
    coin: str = "FNNC",
    github_login: str = None,
    github_id: int = None,
    avatar_url: str = None,
) -> dict:
    """
    Synchronous resolve — calls the Supabase `resolve_worker` RPC.
    Returns a dict with user_id, worker_id, worker_name, coin, enabled.
    Returns None if the prefix is unknown and no github_login was supplied.
    """
    prefix, suffix = parse_worker_name(worker_name)

    result = supabase().rpc(
        "resolve_worker",
        {
            "p_worker_name":  worker_name,
            "p_github_login": github_login,
            "p_github_id":    github_id,
            "p_avatar_url":   avatar_url,
            "p_coin":         coin,
        }
    ).execute()

    rows = result.data
    if not rows:
        log.warning(f"resolve_worker: unknown prefix '{prefix}' for worker '{worker_name}'")
        return None

    row = rows[0]
    log.info(f"Resolved worker '{worker_name}' → user={row['user_id'][:8]}… worker={row['worker_id'][:8]}…")
    return row


def record_share(
    worker_name: str,
    coin: str,
    algo: str,
    difficulty: float,
    accepted: bool = True,
    block_height: int = None,
) -> None:
    """
    Insert a share row. worker_name is the raw Stratum username.
    The worker must already exist (call resolve_worker first on connect).
    """
    worker = (
        supabase()
        .table("workers")
        .select("id")
        .eq("worker_name", worker_name)
        .single()
        .execute()
    )
    if not worker.data:
        log.error(f"record_share: worker '{worker_name}' not found — did resolve_worker run?")
        return

    supabase().table("shares").insert({
        "worker_id":    worker.data["id"],
        "worker_name":  worker_name,
        "coin":         coin,
        "algo":         algo,
        "difficulty":   difficulty,
        "accepted":     accepted,
        "block_height": block_height,
    }).execute()


# ─── Standalone HTTP endpoint ─────────────────────────────────────────────────
# Useful if your Stratum server is in a different language (Go, Rust, etc.)
# and just needs to POST a worker name to resolve it.

async def handle_resolve(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad json"}, status=400)

    worker_name = body.get("worker_name", "").strip()
    coin        = body.get("coin", "FNNC").upper()
    github_login = body.get("github_login")
    github_id    = body.get("github_id")
    avatar_url   = body.get("avatar_url")

    try:
        row = resolve_worker(worker_name, coin, github_login, github_id, avatar_url)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=422)
    except Exception as e:
        log.exception("resolve error")
        return web.json_response({"ok": False, "error": "internal"}, status=500)

    if row is None:
        return web.json_response({"ok": False, "error": "unknown_prefix"}, status=404)

    return web.json_response({"ok": True, **row})


async def handle_share(request: web.Request) -> web.Response:
    """POST /share — called by Stratum server when a share is accepted."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad json"}, status=400)

    required = ("worker_name", "coin", "algo", "difficulty")
    if any(k not in body for k in required):
        return web.json_response({"ok": False, "error": f"missing fields: {required}"}, status=422)

    try:
        record_share(
            worker_name  = body["worker_name"],
            coin         = body["coin"],
            algo         = body["algo"],
            difficulty   = float(body["difficulty"]),
            accepted     = body.get("accepted", True),
            block_height = body.get("block_height"),
        )
    except Exception as e:
        log.exception("share record error")
        return web.json_response({"ok": False, "error": "internal"}, status=500)

    return web.json_response({"ok": True})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "gitmine-resolver"})


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [RESOLVER] %(message)s")
    parser = argparse.ArgumentParser(description="GitMine Worker Resolver HTTP service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()

    app = web.Application()
    app.router.add_post("/resolve", handle_resolve)
    app.router.add_post("/share",   handle_share)
    app.router.add_get("/health",   handle_health)

    print(f"Worker Resolver listening on http://{args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
