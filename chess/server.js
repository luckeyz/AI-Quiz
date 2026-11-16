#!/usr/bin/env node
// Multiplayer chess server. No dependencies: plain HTTP, with server-sent events
// pushing the game to each browser and small JSON POSTs carrying the moves.
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const Chess = require('./public/engine.js');

const PUBLIC = path.join(__dirname, 'public');
const STATIC = {
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/engine.js': ['engine.js', 'text/javascript; charset=utf-8'],
};
const SEAT_GRACE_MS = 20_000;       // how long a disconnected player keeps their seat
const ROOM_IDLE_MS = 60 * 60_000;   // empty rooms are dropped after this long
const ID_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';

const rooms = new Map();

function resetGame(room) {
  room.state = Chess.newGame();
  room.positions = new Map([[Chess.positionKey(room.state), 1]]);
  room.status = Chess.status(room.state, 1);
  room.moves = [];
  room.lastMove = null;
  room.rematch = { w: false, b: false };
}

function createRoom() {
  let id;
  do {
    id = Array.from(crypto.randomBytes(5), (b) => ID_ALPHABET[b % ID_ALPHABET.length]).join('');
  } while (rooms.has(id));
  const room = {
    id,
    players: { w: null, b: null },
    clients: new Map(),    // response -> token
    lastSeen: new Map(),   // token -> time of last disconnect
    emptySince: Date.now(),
  };
  resetGame(room);
  rooms.set(id, room);
  return room;
}

const isOnline = (room, token) => [...room.clients.values()].includes(token);
const seatOf = (room, token) => (room.players.w === token ? 'w' : room.players.b === token ? 'b' : null);

// Returns the caller's colour, seating them if a seat is free or abandoned.
function claimSeat(room, token) {
  const mine = seatOf(room, token);
  if (mine) return mine;
  for (const color of ['w', 'b']) {
    if (!room.players[color]) { room.players[color] = token; return color; }
  }
  for (const color of ['w', 'b']) {
    const holder = room.players[color];
    if (!isOnline(room, holder) && Date.now() - (room.lastSeen.get(holder) || 0) > SEAT_GRACE_MS) {
      room.players[color] = token;
      return color;
    }
  }
  return null;
}

function viewFor(room, token) {
  const seat = (color) => ({
    taken: !!room.players[color],
    online: !!room.players[color] && isOnline(room, room.players[color]),
  });
  return {
    room: room.id,
    you: seatOf(room, token),
    state: room.state,
    status: room.status,
    moves: room.moves,
    lastMove: room.lastMove,
    players: { w: seat('w'), b: seat('b') },
    rematch: room.rematch,
  };
}

function broadcast(room) {
  for (const [res, token] of room.clients) {
    res.write('data: ' + JSON.stringify(viewFor(room, token)) + '\n\n');
  }
}

function playMove(room, color, body) {
  if (room.status.over) return 'The game is over.';
  if (!room.players.w || !room.players.b) return 'Waiting for an opponent.';
  if (room.state.turn !== color) return 'It is not your turn.';
  const promo = typeof body.promo === 'string' ? body.promo.toLowerCase() : undefined;
  const candidates = Chess.legalMoves(room.state).filter((m) => m.from === body.from && m.to === body.to);
  const move = candidates.find((m) => m.promo === promo) || candidates.find((m) => !m.promo || m.promo === 'q');
  if (!move) return 'Illegal move.';

  room.moves.push(Chess.san(room.state, move));
  room.state = Chess.applyMove(room.state, move);
  room.lastMove = { from: move.from, to: move.to };
  const key = Chess.positionKey(room.state);
  const seen = (room.positions.get(key) || 0) + 1;
  room.positions.set(key, seen);
  room.status = Chess.status(room.state, seen);
  return null;
}

function resign(room, color) {
  if (room.status.over) return 'The game is over.';
  room.status = { over: true, check: false, reason: 'resignation', winner: Chess.other(color) };
  return null;
}

function requestRematch(room, color) {
  if (!room.status.over) return 'The game is still in progress.';
  room.rematch[color] = true;
  if (room.rematch.w && room.rematch.b) {
    room.players = { w: room.players.b, b: room.players.w };
    resetGame(room);
  }
  return null;
}

const ACTIONS = { move: playMove, resign, rematch: requestRematch };

function sendJson(res, code, data) {
  res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(data));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 2048) { reject(new Error('too large')); req.destroy(); }
    });
    req.on('end', () => {
      try { resolve(raw ? JSON.parse(raw) : {}); } catch (err) { reject(err); }
    });
    req.on('error', reject);
  });
}

function openStream(req, res, room, token) {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-store',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });
  claimSeat(room, token);
  room.clients.set(res, token);
  room.emptySince = null;
  broadcast(room);

  const ping = setInterval(() => res.write(': ping\n\n'), 25_000);
  req.on('close', () => {
    clearInterval(ping);
    room.clients.delete(res);
    room.lastSeen.set(token, Date.now());
    if (!room.clients.size) room.emptySince = Date.now();
    broadcast(room);
  });
}

async function handle(req, res) {
  const url = new URL(req.url, 'http://localhost');

  if (req.method === 'GET' && STATIC[url.pathname]) {
    const [file, type] = STATIC[url.pathname];
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-cache' });
    return fs.createReadStream(path.join(PUBLIC, file)).pipe(res);
  }

  if (req.method === 'GET' && url.pathname === '/api/rooms') {
    const open = [...rooms.values()].filter((r) => r.players.w && !r.players.b && isOnline(r, r.players.w));
    return sendJson(res, 200, { rooms: open.map((r) => r.id) });
  }

  if (req.method === 'POST' && url.pathname === '/api/rooms') {
    return sendJson(res, 201, { room: createRoom().id });
  }

  const match = url.pathname.match(/^\/api\/rooms\/([A-Za-z0-9]+)\/(events|move|resign|rematch)$/);
  if (!match) return sendJson(res, 404, { error: 'Not found.' });
  const room = rooms.get(match[1].toUpperCase());
  if (!room) return sendJson(res, 404, { error: 'That game does not exist.' });
  const action = match[2];

  if (action === 'events') {
    const token = url.searchParams.get('token');
    if (req.method !== 'GET' || !token || token.length > 64) return sendJson(res, 400, { error: 'Bad request.' });
    return openStream(req, res, room, token);
  }

  if (req.method !== 'POST') return sendJson(res, 405, { error: 'Use POST.' });
  let body;
  try { body = await readJson(req); } catch { return sendJson(res, 400, { error: 'Bad request.' }); }
  const color = seatOf(room, body.token);
  if (!color) return sendJson(res, 403, { error: 'You are watching this game, not playing it.' });
  const error = ACTIONS[action](room, color, body);
  if (error) return sendJson(res, 409, { error });
  broadcast(room);
  return sendJson(res, 200, { ok: true });
}

const server = http.createServer((req, res) => {
  handle(req, res).catch((err) => {
    console.error(err);
    if (!res.headersSent) sendJson(res, 500, { error: 'Server error.' });
    else res.end();
  });
});

setInterval(() => {
  for (const [id, room] of rooms) {
    if (room.emptySince && Date.now() - room.emptySince > ROOM_IDLE_MS) rooms.delete(id);
  }
}, 60_000).unref();

if (require.main === module) {
  const port = Number(process.env.PORT) || 3000;
  server.listen(port, () => console.log(`Chess server running at http://localhost:${port}`));
}

module.exports = { server };
