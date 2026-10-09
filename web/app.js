/* ==========================================================================
   Xadrez — Edição de Clube · frontend
   Dois modos:
     · "ai"     — contra a IA (REST, server.py / server_stdlib.py)
     · "online" — multiplayer em tempo real (WebSocket, /ws)
   O estado autoritativo sempre vive no servidor.
   ========================================================================== */
"use strict";

const API = (window.CHESS_API_BASE || "").replace(/\/$/, "");
const GLYPH = { K: "\u265A", Q: "\u265B", R: "\u265C", B: "\u265D", N: "\u265E", P: "\u265F" };
const VAL = { P: 1, N: 3, B: 3, R: 5, Q: 9, K: 0 };
const ANIM_MS = 180;
const FRAME_PAD = 26;

const $ = (id) => document.getElementById(id);
const boardEl = $("board"), piecesEl = $("pieces"), squaresEl = $("squares"),
      hlEl = $("highlights"), labelsEl = $("labels"), actionsEl = document.querySelector(".actions");

let mode = "ai";           // "ai" | "online"
let state = null;
let gameId = null;         // modo IA
let selected = null;       // [r,c]
let busy = false;
let thinking = false;
let animTo = null;
let humanColor = "w";      // modo IA
let level = "medium";

let net = null;            // ChessNet
let myColor = null;        // "w" | "b" | "spec"
let roomCode = null;
let onlineReady = false;

/* ------------------------------- utilidades ------------------------------ */
function api(path, body) {
  const opt = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : { method: "GET" };
  return fetch(API + path, opt).then(async (res) => {
    if (!res.ok) {
      let msg = res.status;
      try { msg = (await res.json()).detail || msg; } catch (_) { /* ignore */ }
      throw new Error(msg);
    }
    return res.json();
  });
}
const sqPx = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sq")) || 72;

/* Posição inicial local — só para desenhar o tabuleiro enquanto se espera sala. */
function initialState() {
  const back = ["R", "N", "B", "Q", "K", "B", "N", "R"];
  const board = Array.from({ length: 8 }, () => new Array(8).fill(null));
  for (let c = 0; c < 8; c++) {
    board[0][c] = "b" + back[c];
    board[1][c] = "bP";
    board[6][c] = "wP";
    board[7][c] = "w" + back[c];
  }
  return {
    board, turn: "w", human_color: "spec", ai_color: null, level: "medium",
    legal: [], last_move: null, history: [], captured: { w: [], b: [] },
    game_over: false, result: "", winner: null, check: false, check_square: null,
    anim: null, mode: "online",
  };
}

/* ------------------------------- tabuleiro ------------------------------- */
function computeSquare() {
  const w = window.innerWidth;
  const avail = w > 900 ? Math.min(576, w - 440) : Math.min(576, w - 96);
  return Math.max(30, Math.min(72, Math.floor(avail / 8)));
}

function buildBoard() {
  const sq = computeSquare();
  document.documentElement.style.setProperty("--sq", sq + "px");

  squaresEl.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const d = document.createElement("div");
      d.className = "sq " + ((r + c) % 2 === 0 ? "light" : "dark");
      frag.appendChild(d);
    }
  }
  squaresEl.appendChild(frag);

  labelsEl.innerHTML = "";
  for (let c = 0; c < 8; c++) {
    const f = document.createElement("span");
    f.className = "file";
    f.textContent = "abcdefgh"[c];
    f.style.left = (c * sq + sq / 2) + "px";
    f.style.top = (8 * sq + FRAME_PAD / 2) + "px";
    labelsEl.appendChild(f);
  }
  for (let r = 0; r < 8; r++) {
    const n = document.createElement("span");
    n.className = "rank";
    n.textContent = String(8 - r);
    n.style.left = (-FRAME_PAD / 2) + "px";
    n.style.top = (r * sq + sq / 2) + "px";
    labelsEl.appendChild(n);
  }
}

/* -------------------------------- render --------------------------------- */
function render() {
  if (!state) return;
  const sq = sqPx();
  renderHighlights(sq);
  renderPieces(sq);
  renderPanel();
}

function renderHighlights(sq) {
  hlEl.innerHTML = "";
  const add = (r, c, cls) => {
    const d = document.createElement("div");
    d.className = "hl " + cls;
    d.style.left = (c * sq) + "px";
    d.style.top = (r * sq) + "px";
    hlEl.appendChild(d);
  };
  if (state.last_move) {
    add(state.last_move[0], state.last_move[1], "last");
    add(state.last_move[2], state.last_move[3], "last");
  }
  if (state.check_square) add(state.check_square[0], state.check_square[1], "check");
  if (selected) add(selected[0], selected[1], "sel");
  if (selected && canMoveNow()) {
    for (const m of state.legal) {
      if (m[0] === selected[0] && m[1] === selected[1]) {
        add(m[2], m[3], state.board[m[2]][m[3]] ? "ring" : "dot");
      }
    }
  }
}

function renderPieces(sq) {
  piecesEl.innerHTML = "";
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const p = state.board[r][c];
      if (!p) continue;
      if (animTo && animTo[0] === r && animTo[1] === c) continue;
      piecesEl.appendChild(pieceEl(p, r, c, sq));
    }
  }
}

function pieceEl(code, r, c, sq, extra) {
  const span = document.createElement("span");
  span.className = "piece " + (code[0] === "w" ? "w" : "b") + (extra ? " " + extra : "");
  span.textContent = GLYPH[code[1]];
  span.style.left = (c * sq) + "px";
  span.style.top = (r * sq) + "px";
  return span;
}

function canMoveNow() {
  if (!state || state.game_over || busy || thinking) return false;
  if (mode === "online") return onlineReady && state.turn === state.human_color;
  return state.turn === state.human_color;
}

function renderPanel() {
  let main, sub;
  if (state.game_over) { main = "PARTIDA ENCERRADA"; sub = state.result; }
  else if (thinking) { main = "IA PENSANDO"; sub = "avaliando posições…"; }
  else {
    main = state.turn === "w" ? "VEZ DAS BRANCAS" : "VEZ DAS PRETAS";
    if (mode === "online") {
      if (!onlineReady) sub = "aguardando oponente…";
      else sub = state.turn === state.human_color ? "seu lance" : "lance do oponente";
    } else {
      sub = state.turn === state.human_color ? "seu lance" : "lance da IA";
    }
  }
  $("turnMain").textContent = main;
  $("turnSub").textContent = sub;

  const sw = $("swatch");
  sw.style.background = state.game_over || thinking ? "" : (state.turn === "w" ? "#F5EFE0" : "#221E18");
  if (state.game_over) $("statusText").textContent = state.result;
  else if (thinking) $("statusText").textContent = "IA pensando…";
  else $("statusText").textContent = state.turn === "w" ? "Vez das Brancas" : "Vez das Pretas";

  document.querySelectorAll("#levels button").forEach((b) =>
    b.classList.toggle("active", b.dataset.level === state.level));

  // Notação
  const moves = $("moves");
  moves.innerHTML = "";
  const rows = 8;
  const total = Math.ceil(state.history.length / 2);
  const start = Math.max(0, total - rows);
  const frag = document.createDocumentFragment();
  for (let i = start; i < total; i++) {
    const row = document.createElement("div");
    row.className = "row" + (i === total - 1 ? " last" : "");
    const w = state.history[2 * i] ? state.history[2 * i].san : "";
    const b = state.history[2 * i + 1] ? state.history[2 * i + 1].san : "";
    row.innerHTML = `<span>${i + 1}.</span><span>${w}</span><span>${b}</span>`;
    frag.appendChild(row);
  }
  moves.appendChild(frag);

  // Capturadas + vantagem
  const caps = $("caps");
  caps.innerHTML = "";
  const diff = materialDiff();
  for (const side of ["w", "b"]) {
    const row = document.createElement("div");
    row.className = "cap-row";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = side === "w" ? "BRANCAS" : "PRETAS";
    row.appendChild(label);
    const list = state.captured[side].slice().sort((a, b) => VAL[b[1]] - VAL[a[1]]);
    for (const p of list) {
      const g = document.createElement("span");
      g.className = "glyph " + (p[0] === "w" ? "w" : "b");
      g.textContent = GLYPH[p[1]];
      row.appendChild(g);
    }
    if ((side === "w" && diff > 0) || (side === "b" && diff < 0)) {
      const adv = document.createElement("span");
      adv.className = "adv";
      adv.textContent = "+" + Math.abs(diff);
      row.appendChild(adv);
    }
    caps.appendChild(row);
  }

  $("undoBtn").disabled = busy || thinking || state.history.length === 0;

  // Overlay
  const ov = $("overlay");
  if (state.game_over) {
    ov.hidden = false;
    $("overlayTitle").textContent = state.result;
    $("overlayHint").textContent = mode === "online"
      ? "Use REVANCHE para jogar de novo"
      : "Pressione N para novo jogo";
  } else {
    ov.hidden = true;
  }

  updateActions();
}

function materialDiff() {
  const sum = (arr) => arr.reduce((s, p) => s + VAL[p[1]], 0);
  return sum(state.captured.w) - sum(state.captured.b);
}

function updateActions() {
  const isAI = mode === "ai";
  $("newBtn").hidden = !isAI;
  $("undoBtn").hidden = !isAI;
  const canRematch = mode === "online" && state && state.game_over &&
    (myColor === "w" || myColor === "b");
  $("rematchBtn").hidden = !canRematch;
  actionsEl.classList.toggle("one", !isAI && canRematch);
}

/* ------------------------------ animação --------------------------------- */
function animate(anim) {
  return new Promise((resolve) => {
    if (!anim) return resolve();
    const sq = sqPx();
    const [fr, fc] = anim.from, [tr, tc] = anim.to;
    const dx = (tc - fc) * sq, dy = (tr - fr) * sq;
    const ease = "cubic-bezier(0.33,1,0.68,1)";

    const fly = pieceEl(anim.piece, fr, fc, sq, "fly");
    const shadow = document.createElement("div");
    shadow.className = "contact";
    shadow.style.left = (fc * sq) + "px";
    shadow.style.top = (fr * sq) + "px";
    piecesEl.appendChild(shadow);
    piecesEl.appendChild(fly);

    if (anim.captured) {
      const cap = pieceEl(anim.captured, tr, tc, sq, "");
      piecesEl.appendChild(cap);
      const a = cap.animate(
        [{ opacity: 1 }, { opacity: 1, offset: 0.2 }, { opacity: 0 }],
        { duration: ANIM_MS, easing: "ease-out" });
      a.addEventListener("finish", () => cap.remove());
    }

    const flyAnim = fly.animate([
      { transform: "translate(0,0)" },
      { transform: `translate(${dx * 0.5}px,${dy * 0.5 - 9}px)`, offset: 0.5 },
      { transform: `translate(${dx}px,${dy}px)` },
    ], { duration: ANIM_MS, easing: ease });

    shadow.animate([
      { transform: "translate(0,0) scale(1)", opacity: 0.5 },
      { transform: `translate(${dx * 0.5}px,${dy * 0.5}px) scale(0.8)`, offset: 0.5, opacity: 0.3 },
      { transform: `translate(${dx}px,${dy}px) scale(1)`, opacity: 0.5 },
    ], { duration: ANIM_MS, easing: ease });

    const done = () => { fly.remove(); shadow.remove(); resolve(); };
    flyAnim.finished.then(done).catch(done);
  });
}

/* ============================ Modo IA (REST) ============================= */
async function newGame(color) {
  busy = true; thinking = false;
  humanColor = color || humanColor;
  try {
    const res = await api("/api/new", { level, human_color: humanColor });
    gameId = res.game_id;
    state = res.state;
    selected = null; animTo = null;
    document.querySelectorAll("#colors button").forEach((b) =>
      b.classList.toggle("active", b.dataset.color === humanColor));
    render();
    setConn(true);
    if (!state.game_over && state.turn === state.ai_color) await aiTurn();
  } catch (e) { setConn(false); alert("Não foi possível iniciar: " + e.message); }
  busy = false;
  render();
}

async function playHuman(move) {
  if (mode === "online") {
    busy = true; selected = null; render();
    net.send({ type: "move", move });
    return;
  }
  busy = true;
  try {
    const res = await api("/api/move", { game_id: gameId, move });
    state = res.state; selected = null;
    animTo = state.anim ? state.anim.to : null;
    render();
    await animate(state.anim);
    animTo = null; render();
    if (!state.game_over && state.turn === state.ai_color) await aiTurn();
    setConn(true);
  } catch (e) { setConn(false); }
  busy = false;
  render();
}

async function aiTurn() {
  thinking = true; render();
  try {
    const res = await api("/api/ai", { game_id: gameId });
    state = res.state;
    animTo = state.anim ? state.anim.to : null;
    render();
    await animate(state.anim);
    animTo = null;
  } catch (e) { setConn(false); }
  thinking = false;
  render();
}

async function undo() {
  if (mode !== "ai" || busy || thinking || !gameId) return;
  busy = true;
  try {
    const res = await api("/api/undo", { game_id: gameId });
    state = res.state; selected = null; animTo = null;
    render(); setConn(true);
  } catch (e) { setConn(false); }
  busy = false;
  render();
}

async function setLevel(l) {
  level = l;
  document.querySelectorAll("#levels button").forEach((b) =>
    b.classList.toggle("active", b.dataset.level === l));
  if (mode === "ai" && gameId && state && !state.game_over) {
    try { const res = await api("/api/level", { game_id: gameId, level: l }); state = res.state; render(); }
    catch (e) { setConn(false); }
  }
}

/* ========================== Modo online (WebSocket) ====================== */
function connectNet() {
  if (!net) return;
  net.connect();
}

function doCreate() { net.send({ type: "create", name: myName(), pid: myPid() }); }
function doJoin() {
  const code = $("joinInput").value.trim().toUpperCase();
  if (code.length < 4) return flash("digite o código de 4 letras");
  net.send({ type: "join", code, name: myName(), pid: myPid() });
}
function doQueue() {
  $("queueBtn").textContent = "PROCURANDO…";
  $("queueBtn").disabled = true;
  net.send({ type: "queue", name: myName(), pid: myPid() });
}
function doLeave() {
  net.send({ type: "leave" });
  resetRoomUi();
  state = initialState(); selected = null; render();
}
function doRematch() { net.send({ type: "rematch" }); }

function myName() {
  let n = localStorage.getItem("xadrez.nome");
  if (!n) {
    n = prompt("Seu nome na partida:", "Jogador") || "Jogador";
    n = n.trim().slice(0, 20) || "Jogador";
    localStorage.setItem("xadrez.nome", n);
  }
  return n;
}
function myPid() {
  let pid = localStorage.getItem("xadrez.pid");
  if (!pid) {
    pid = (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("xadrez.pid", pid);
  }
  return pid;
}

/* -------------------------------- ranking -------------------------------- */
let myProfile = null;
async function loadRanking() {
  try {
    const res = await api("/api/ranking?limit=20");
    renderRanking(res);
  } catch (_) { /* servidor fora do ar: silencioso */ }
}

function renderRanking(res) {
  const list = $("rankList");
  list.innerHTML = "";
  const top = (res && res.top) || [];
  if (top.length === 0) {
    const d = document.createElement("div");
    d.className = "rank-empty";
    d.textContent = "Ninguém pontuou ainda. Jogue online para entrar!";
    list.appendChild(d);
    return;
  }
  const myId = myPid();
  for (const p of top) {
    const row = document.createElement("div");
    row.className = "row" + (p.id === myId ? " me" : "");
    const pos = document.createElement("span");
    pos.className = "pos"; pos.textContent = p.rank;
    const nm = document.createElement("span");
    nm.className = "nm";
    const n = document.createElement("span");
    n.className = "n"; n.textContent = p.name + (p.id === myId ? " (você)" : "");
    const rec = document.createElement("span");
    rec.className = "rec"; rec.textContent = `${p.wins}V ${p.draws}E ${p.losses}D`;
    nm.appendChild(n); nm.appendChild(rec);
    const rt = document.createElement("span");
    rt.className = "rt"; rt.textContent = p.rating;
    row.append(pos, nm, rt);
    list.appendChild(row);
  }
}

function setMyProfile(prof, delta) {
  const el = $("rankMe");
  if (!prof) { el.textContent = "—"; return; }
  myProfile = prof;
  let t = `${prof.name} · ${prof.rating}`;
  if (prof.rank) t += ` (nº ${prof.rank})`;
  if (delta) t += `  ${delta > 0 ? "+" : ""}${delta}`;
  el.textContent = t;
}

function copyLink() {
  const url = location.origin + location.pathname + "?sala=" + roomCode;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(() => flash("link copiado!"), () => prompt("Copie o link:", url));
  } else {
    prompt("Copie o link:", url);
  }
}

function resetRoomUi() {
  roomCode = null; myColor = null; onlineReady = false;
  $("room").hidden = true;
  $("lobby").hidden = false;
  $("queueBtn").textContent = "JOGAR AGORA (fila)";
  $("queueBtn").disabled = false;
  $("chat").innerHTML = "";
}

/* ---------------------- eventos vindos do servidor ------------------------ */
function onCreated(msg) { roomCode = msg.code; }

function onRoom(msg) {
  roomCode = msg.code;
  myColor = msg.you;
  onlineReady = msg.status === "playing";
  $("lobby").hidden = true;
  $("room").hidden = false;
  $("roomCode").textContent = msg.code;

  const nm = (c) => msg.names[c] || (c === "w" ? "Brancas" : "Pretas");
  let line = "você: " + (msg.you === "spec" ? "espectador" : nm(msg.you));
  if (msg.you === "w" || msg.you === "b") line += " (" + (msg.you === "w" ? "brancas" : "pretas") + ")";
  $("roomPlayers").textContent = line;

  if (msg.status === "playing") $("roomStatus").textContent = "partida em andamento";
  else $("roomStatus").textContent = "aguardando oponente…";

  updateActions();
  render();
}

async function onState(msg) {
  state = msg.state;
  selected = null;
  const anim = state.anim;
  animTo = anim ? anim.to : null;
  render();
  if (anim) {
    busy = true;
    await animate(anim);
    animTo = null;
  }
  busy = false;
  render();
}

function onChat(msg) {
  appendChat(msg.from === myColor ? "me" : "other", msg.name, msg.text);
}

function onSys(msg) { appendChat("sys", "", msg.text); }

function onQueued() {
  $("lobby").hidden = false;
  $("queueBtn").textContent = "PROCURANDO OPONENTE…";
  $("queueBtn").disabled = true;
}

function onError(msg) {
  busy = false;
  thinking = false;
  render();
  flash(msg.message || "erro");
}

function appendChat(kind, who, text) {
  const div = document.createElement("div");
  div.className = "msg" + (kind === "sys" ? " sys" : "") + (kind === "me" ? " me" : "");
  if (kind === "sys") {
    div.textContent = text;
  } else {
    const w = document.createElement("span");
    w.className = "who";
    w.textContent = who + ": ";
    div.appendChild(w);
    div.appendChild(document.createTextNode(text));
  }
  const chat = $("chat");
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  while (chat.children.length > 60) chat.removeChild(chat.firstChild);
}

function sendChat() {
  const inp = $("chatInput");
  const t = inp.value.trim();
  if (!t) return;
  net.send({ type: "chat", text: t });
  inp.value = "";
}

/* -------------------------------- conexão ------------------------------- */
function setConn(ok) {
  const el = $("conn");
  el.textContent = ok ? "conectado ao servidor" : "sem conexão com o servidor";
  el.classList.toggle("off", !ok);
}

let flashTimer = null;
function flash(msg) {
  const el = $("conn");
  el.textContent = msg;
  el.classList.remove("off");
  clearTimeout(flashTimer);
  flashTimer = setTimeout(refreshConn, 2600);
}

function refreshConn() {
  if (mode !== "online") return;
  const el = $("conn");
  const ok = !!(net && net.connected);
  el.textContent = ok ? "conectado (online)" : "sem conexão — tentando…";
  el.classList.toggle("off", !ok);
}

/* --------------------------------- modo --------------------------------- */
function setMode(m) {
  if (m === mode) return;
  if (m === "online") enterOnline();
  else exitOnline();
}

function enterOnline() {
  mode = "online";
  document.querySelectorAll("#modes button").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === "online"));
  $("aiPanel").hidden = true;
  $("onlinePanel").hidden = false;
  $("chatSection").hidden = false;
  state = initialState(); selected = null; animTo = null;
  resetRoomUi();
  render();
  connectNet();
  updateActions();
}

function exitOnline() {
  mode = "ai";
  document.querySelectorAll("#modes button").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === "ai"));
  $("onlinePanel").hidden = true;
  $("aiPanel").hidden = false;
  $("chatSection").hidden = true;
  if (net) net.disconnect();
  resetRoomUi();
  setConn(true);
  newGame(humanColor);
}

/* ------------------------------- interação ------------------------------- */
function onBoardClick(ev) {
  if (!state || busy || thinking || state.game_over) return;
  if (mode === "online") {
    if (!onlineReady || state.turn !== state.human_color) return;
  } else if (state.turn !== state.human_color) {
    return;
  }
  const rect = boardEl.getBoundingClientRect();
  const sq = sqPx();
  const c = Math.floor((ev.clientX - rect.left) / sq);
  const r = Math.floor((ev.clientY - rect.top) / sq);
  if (r < 0 || r > 7 || c < 0 || c > 7) return;

  const piece = state.board[r][c];
  if (selected) {
    const isTarget = state.legal.some((m) =>
      m[0] === selected[0] && m[1] === selected[1] && m[2] === r && m[3] === c);
    if (isTarget) { playHuman([selected[0], selected[1], r, c]); return; }
    if (piece && piece[0] === state.human_color) { selected = [r, c]; render(); return; }
    selected = null; render(); return;
  }
  if (piece && piece[0] === state.human_color) { selected = [r, c]; render(); }
}

boardEl.addEventListener("click", onBoardClick);
document.querySelectorAll("#modes button").forEach((b) =>
  b.addEventListener("click", () => setMode(b.dataset.mode)));
document.querySelectorAll("#levels button").forEach((b) =>
  b.addEventListener("click", () => setLevel(b.dataset.level)));
document.querySelectorAll("#colors button").forEach((b) =>
  b.addEventListener("click", () => newGame(b.dataset.color)));
$("newBtn").addEventListener("click", () => newGame(humanColor));
$("undoBtn").addEventListener("click", undo);
$("rematchBtn").addEventListener("click", doRematch);
$("createBtn").addEventListener("click", doCreate);
$("joinBtn").addEventListener("click", doJoin);
$("joinInput").addEventListener("keydown", (e) => { if (e.key === "Enter") doJoin(); });
$("joinInput").addEventListener("input", (e) => {
  e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4);
});
$("queueBtn").addEventListener("click", doQueue);
$("leaveBtn").addEventListener("click", doLeave);
$("copyBtn").addEventListener("click", copyLink);
$("rankRefresh").addEventListener("click", loadRanking);
$("chatSend").addEventListener("click", sendChat);
$("chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

document.addEventListener("keydown", (e) => {
  if (mode !== "ai") return;
  if (e.key === "n" || e.key === "N") newGame(humanColor);
  else if (e.key === "u" || e.key === "U") undo();
  else if (e.key === "1") setLevel("easy");
  else if (e.key === "2") setLevel("medium");
  else if (e.key === "3") setLevel("hard");
});

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { buildBoard(); render(); }, 120);
});

/* -------------------------------- início --------------------------------- */
buildBoard();
net = new ChessNet();
net.onStatus(refreshConn);
net.on("created", onCreated);
net.on("room", onRoom);
net.on("state", onState);
net.on("chat", onChat);
net.on("sys", onSys);
net.on("queued", onQueued);
net.on("error", onError);
net.on("rating", (m) => { setMyProfile(m.profile, m.delta); loadRanking(); });
net.on("ranking_refresh", () => loadRanking());

loadRanking();

const entrada = (new URLSearchParams(location.search).get("sala") || "").trim().toUpperCase();
if (entrada.length === 4) {
  enterOnline();
  $("joinInput").value = entrada;
  net.send({ type: "join", code: entrada, name: myName(), pid: myPid() });
  flash("entrando na sala " + entrada + "…");
} else {
  newGame("w");
}
