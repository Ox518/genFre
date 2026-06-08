# GitMine Relay (Optional)

The Relay bridge is **not required** to run the pool. The pool operates entirely via GitHub Actions + GitHub Pages.

The Relay was originally a WebSocket server for live dashboard updates. It has been removed from the core pool architecture. The dashboard auto-refreshes from `docs/stats.json` every 30 seconds.

## If you want real-time updates

Consider a GitHub webhook forwarded to a static WebSocket server, or simply rely on the 30s polling.

## Pool Architecture (current)

```
Miners → git push commits → shares-pending branch
       → GitHub Actions validates + updates stats
       → docs/stats.json committed to main
       → GitHub Pages serves dashboard
       → Dashboard polls every 30s
```

No relay server needed.
