/* ==========================================================================
   Xadrez — Edição de Clube · cliente WebSocket (multiplayer)
   Fino de propósito: só conecta, envia e dispara callbacks por tipo de msg.
   ========================================================================== */
"use strict";

(function () {
  function wsUrl() {
    const base = (window.CHESS_API_BASE || "").replace(/\/$/, "");
    if (base) return base.replace(/^http/, "ws") + "/ws";
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return proto + "://" + location.host + "/ws";
  }

  class ChessNet {
    constructor() {
      this.ws = null;
      this.handlers = {};
      this.connected = false;
      this.want = false;        // o usuário quer estar conectado
      this._outbox = [];
      this._statusCb = null;
      this._retry = null;
    }

    on(type, cb) { (this.handlers[type] || (this.handlers[type] = [])).push(cb); return this; }
    onStatus(cb) { this._statusCb = cb; return this; }
    _emit(type, payload) { (this.handlers[type] || []).forEach((cb) => cb(payload)); }
    _status(ok) { if (this._statusCb) this._statusCb(ok); }

    connect() {
      this.want = true;
      if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
      this.ws = new WebSocket(wsUrl());

      this.ws.onopen = () => {
        this.connected = true;
        this._status(true);
        this._outbox.forEach((m) => this.ws.send(m));
        this._outbox = [];
      };
      this.ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch (_) { return; }
        this._emit(msg.type, msg);
        this._emit("*", msg);
      };
      this.ws.onclose = () => {
        this.connected = false;
        this._status(false);
        if (this.want) {           // reconecta sozinho se a queda foi acidental
          clearTimeout(this._retry);
          this._retry = setTimeout(() => this.connect(), 1200);
        }
      };
      this.ws.onerror = () => { /* o onclose trata */ };
    }

    send(obj) {
      const text = JSON.stringify(obj);
      if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(text);
      else { this._outbox.push(text); this.connect(); }
    }

    disconnect() {
      this.want = false;
      clearTimeout(this._retry);
      if (this.ws) this.ws.close();
      this.ws = null;
      this.connected = false;
    }
  }

  window.ChessNet = ChessNet;
})();
