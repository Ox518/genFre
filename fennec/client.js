/**
 * GitMine TTY — Fennec WebSocket Client
 * Isomorphic: works in browser (PWA dashboard) and Node.js (TUI command)
 *
 * Usage (browser):
 *   import { FennecClient } from './fennec/client.js';
 *   const fennec = new FennecClient('ws://192.168.1.100:8765');
 *   fennec.on('state_update', (msg) => updateDashboard(msg));
 *   fennec.on('share_submitted', (msg) => flashShareCounter(msg));
 *   fennec.connect();
 *
 * Usage (Node.js / TUI):
 *   const { FennecClient } = require('./fennec/client.js');
 *   const fennec = new FennecClient(process.env.FENNEC_URL);
 *   fennec.on('heartbeat', ({ rig_id }) => markRigOnline(rig_id));
 *   fennec.connect();
 */

export class FennecClient {
  constructor(url, options = {}) {
    this.url = url;
    this.options = {
      reconnectInterval: options.reconnectInterval ?? 5000,
      debug: options.debug ?? false,
    };
    this._handlers = {};
    this._ws = null;
    this._reconnectTimer = null;
    this._connected = false;
    this._intentionalClose = false;
  }

  on(eventType, handler) {
    if (!this._handlers[eventType]) this._handlers[eventType] = [];
    this._handlers[eventType].push(handler);
    return this; // chainable
  }

  off(eventType, handler) {
    if (this._handlers[eventType]) {
      this._handlers[eventType] = this._handlers[eventType].filter(h => h !== handler);
    }
    return this;
  }

  _emit(eventType, data) {
    const handlers = this._handlers[eventType] || [];
    const wildcards = this._handlers['*'] || [];
    [...handlers, ...wildcards].forEach(h => h(data));
  }

  connect() {
    this._intentionalClose = false;
    this._log(`Connecting to Fennec at ${this.url}`);

    // Browser uses native WebSocket; Node.js uses 'ws' package
    const WSImpl = typeof WebSocket !== 'undefined' ? WebSocket : require('ws');
    this._ws = new WSImpl(this.url);

    this._ws.onopen = () => {
      this._connected = true;
      clearTimeout(this._reconnectTimer);
      this._log('Connected');
      this._emit('connected', { url: this.url });
    };

    this._ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = msg.subtype || msg.type || 'unknown';
        this._log(`← [${type}]`, msg);
        this._emit(type, msg);
        this._emit('message', msg); // catch-all
      } catch (e) {
        this._log('Parse error', event.data);
      }
    };

    this._ws.onclose = (event) => {
      this._connected = false;
      this._emit('disconnected', { code: event.code, reason: event.reason });
      if (!this._intentionalClose) {
        this._log(`Disconnected. Reconnecting in ${this.options.reconnectInterval}ms...`);
        this._reconnectTimer = setTimeout(() => this.connect(), this.options.reconnectInterval);
      }
    };

    this._ws.onerror = (err) => {
      this._emit('error', err);
      this._log('Error', err);
    };
  }

  send(type, data = {}) {
    if (this._connected && this._ws?.readyState === 1) {
      this._ws.send(JSON.stringify({ type, ...data }));
    }
  }

  ping() { this.send('ping'); }
  status() { this.send('status'); }

  disconnect() {
    this._intentionalClose = true;
    clearTimeout(this._reconnectTimer);
    this._ws?.close();
  }

  get isConnected() { return this._connected; }

  _log(...args) {
    if (this.options.debug) console.log('[FennecClient]', ...args);
  }
}
