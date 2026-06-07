#!/usr/bin/env python3
"""
GitMine TTY — Fennec WebSocket Bridge

Replaces Cloudflare Workers entirely. Fennec is a lightweight, self-hosted
WebSocket broadcaster that:
  - Listens for GitHub webhook POST events (pool operator Action)
  - Rebroadcasts state updates to all connected dashboard/TUI clients
  - Runs on the miner's own machine, home server, or ANY Linux box
  - Zero cloud dependency. Zero external accounts.

Requirements:
  pip install websockets aiohttp pyyaml

Usage:
  python fennec/bridge.py --config config/pool.yaml
  # or as a systemd service (see fennec/gitmine-fennec.service)

Clients connect to:
  ws://<your-ip>:8765/ws

Webhook endpoint (configure in GitHub repo settings):
  http://<your-ip>:8765/webhook
"""

import asyncio
import json
import hashlib
import hmac
import logging
import argparse
from datetime import datetime
from typing import Set

import yaml
import websockets
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FENNEC] %(levelname)s %(message)s"
)
log = logging.getLogger("fennec")


class FennecBridge:
    def __init__(self, config: dict):
        self.config = config
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.webhook_secret = config.get("operator", {}).get("webhook_secret", "")
        self.host = config.get("operator", {}).get("fennec_host", "0.0.0.0")
        self.port = config.get("operator", {}).get("fennec_port", 8765)
        self.stats = {
            "started_at": datetime.utcnow().isoformat(),
            "messages_broadcast": 0,
            "clients_connected": 0,
            "clients_peak": 0,
        }

    async def register(self, ws: websockets.WebSocketServerProtocol):
        self.clients.add(ws)
        self.stats["clients_connected"] = len(self.clients)
        self.stats["clients_peak"] = max(self.stats["clients_peak"], len(self.clients))
        log.info(f"Client connected: {ws.remote_address} | Total: {len(self.clients)}")
        # Send current stats snapshot on connect
        try:
            await ws.send(json.dumps({
                "type": "connected",
                "fennec": self.stats
            }))
        except Exception:
            pass

    async def unregister(self, ws: websockets.WebSocketServerProtocol):
        self.clients.discard(ws)
        self.stats["clients_connected"] = len(self.clients)
        log.info(f"Client disconnected: {ws.remote_address} | Remaining: {len(self.clients)}")

    async def broadcast(self, message: dict):
        if not self.clients:
            return
        payload = json.dumps(message)
        self.stats["messages_broadcast"] += 1
        dead = set()
        for ws in self.clients:
            try:
                await ws.send(payload)
            except websockets.exceptions.ConnectionClosed:
                dead.add(ws)
        for ws in dead:
            await self.unregister(ws)

    async def ws_handler(self, ws: websockets.WebSocketServerProtocol, path: str):
        """Handle WebSocket connections from dashboards and TUI clients."""
        await self.register(ws)
        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                    # Clients can ping or request status
                    if data.get("type") == "ping":
                        await ws.send(json.dumps({"type": "pong", "ts": datetime.utcnow().isoformat()}))
                    elif data.get("type") == "status":
                        await ws.send(json.dumps({"type": "status", "fennec": self.stats}))
                except json.JSONDecodeError:
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(ws)

    def verify_github_signature(self, body: bytes, signature: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        if not self.webhook_secret:
            return True  # No secret configured, allow all (dev mode)
        expected = "sha256=" + hmac.new(
            self.webhook_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def webhook_handler(self, request: web.Request) -> web.Response:
        """Receive GitHub webhook events and broadcast to connected clients."""
        body = await request.read()
        sig = request.headers.get("X-Hub-Signature-256", "")

        if not self.verify_github_signature(body, sig):
            log.warning("Webhook signature verification failed")
            return web.Response(status=403, text="Forbidden")

        event = request.headers.get("X-GitHub-Event", "unknown")
        delivery = request.headers.get("X-GitHub-Delivery", "")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return web.Response(status=400, text="Bad JSON")

        # Build broadcast message
        broadcast_msg = {
            "type": "github_event",
            "event": event,
            "delivery": delivery,
            "ts": datetime.utcnow().isoformat(),
        }

        # Parse meaningful fields per event type
        if event == "push":
            ref = payload.get("ref", "")
            branch = ref.replace("refs/heads/", "")
            broadcast_msg["branch"] = branch
            broadcast_msg["commits"] = len(payload.get("commits", []))
            broadcast_msg["pusher"] = payload.get("pusher", {}).get("name", "")

            # Classify push type
            if branch == "shares-pending":
                broadcast_msg["subtype"] = "share_submitted"
            elif branch.startswith("fleet/") and branch.endswith("/heartbeat"):
                rig_id = branch.split("/")[1]
                broadcast_msg["subtype"] = "heartbeat"
                broadcast_msg["rig_id"] = rig_id
            elif branch == "main":
                broadcast_msg["subtype"] = "state_update"

        elif event == "workflow_run":
            broadcast_msg["workflow"] = payload.get("workflow_run", {}).get("name", "")
            broadcast_msg["status"] = payload.get("workflow_run", {}).get("status", "")
            broadcast_msg["conclusion"] = payload.get("workflow_run", {}).get("conclusion", "")

        elif event == "create":
            broadcast_msg["ref_type"] = payload.get("ref_type", "")
            broadcast_msg["ref"] = payload.get("ref", "")
            if "template-" in broadcast_msg.get("ref", ""):
                broadcast_msg["subtype"] = "new_template"

        await self.broadcast(broadcast_msg)
        log.info(f"Webhook [{event}] broadcast to {len(self.clients)} clients")
        return web.Response(text="OK")

    async def health_handler(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "bridge": "gitmine-fennec",
            "version": "1.0.0",
            **self.stats
        })

    async def run(self):
        log.info(f"Fennec Bridge starting on {self.host}:{self.port}")

        # HTTP app for webhooks + health
        app = web.Application()
        app.router.add_post("/webhook", self.webhook_handler)
        app.router.add_get("/health", self.health_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        http_site = web.TCPSite(runner, self.host, self.port + 1)  # port+1 for HTTP
        await http_site.start()
        log.info(f"HTTP webhook listener on {self.host}:{self.port + 1}")

        # WebSocket server for dashboard/TUI clients
        ws_server = await websockets.serve(
            self.ws_handler,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
        )
        log.info(f"WebSocket server on ws://{self.host}:{self.port}/ws")
        log.info("Fennec Bridge ready. Waiting for connections...")

        await asyncio.gather(
            ws_server.wait_closed(),
            asyncio.sleep(float("inf")),
        )


def main():
    parser = argparse.ArgumentParser(description="GitMine TTY Fennec WebSocket Bridge")
    parser.add_argument("--config", default="config/pool.yaml", help="Path to pool.yaml")
    parser.add_argument("--port", type=int, help="Override WebSocket port")
    parser.add_argument("--host", help="Override bind host")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    if args.port:
        config["operator"]["fennec_port"] = args.port
    if args.host:
        config["operator"]["fennec_host"] = args.host

    bridge = FennecBridge(config)
    asyncio.run(bridge.run())


if __name__ == "__main__":
    main()
