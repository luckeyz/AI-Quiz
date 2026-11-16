/* global Chess */
(() => {
  const $ = (id) => document.getElementById(id);
  const GLYPH = { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' };
  const NAME = { k: 'king', q: 'queen', r: 'rook', b: 'bishop', n: 'knight', p: 'pawn' };
  const VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9 };
  const START_COUNT = { p: 8, n: 2, b: 2, r: 2, q: 1 };
  const COLOR = { w: 'White', b: 'Black' };
  // The text-presentation selector stops phones drawing the pawn as an emoji.
  const glyph = (piece) => GLYPH[piece.toLowerCase()] + '︎';

  let room = null;       // current room code
  let stream = null;     // EventSource for the room
  let view = null;       // latest snapshot from the server
  let state = null;      // position on screen (may be one move ahead of the server)
  let selected = null;   // square of the piece chosen on the remote
  let promotion = null;  // {from, to} while choosing a promotion piece
  let resignArmed = false;

  function token() {
    let t = sessionStorage.getItem('chess-token');
    if (!t) {
      t = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
      sessionStorage.setItem('chess-token', t);
    }
    return t;
  }

  async function post(action, body) {
    const res = await fetch(`/api/rooms/${room}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token(), ...body }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'Something went wrong.');
  }

  // ---- Lobby ---------------------------------------------------------------

  let lobbyTimer = null;

  async function refreshOpenGames() {
    let codes = [];
    try { codes = (await (await fetch('/api/rooms')).json()).rooms; } catch { /* keep the list empty */ }
    if ($('lobby').hidden) return;
    const list = $('openGames');
    list.textContent = '';
    for (const code of codes) {
      const el = Object.assign(document.createElement('button'), { className: 'btn', textContent: 'Join ' + code });
      el.onclick = () => enterRoom(code);
      list.append(el);
    }
    $('noGames').hidden = codes.length > 0;
  }

  function showLobby(message) {
    if (stream) stream.close();
    stream = null; room = null; view = null; state = null;
    $('game').hidden = true;
    $('lobby').hidden = false;
    $('roomCode').textContent = '';
    $('lobbyError').textContent = message || '';
    if (location.hash) history.replaceState(null, '', location.pathname);
    refreshOpenGames();
    clearInterval(lobbyTimer);
    lobbyTimer = setInterval(refreshOpenGames, 3000);
  }

  function enterRoom(code) {
    room = code.toUpperCase();
    selected = null; promotion = null; view = null;
    if (location.hash.slice(1) !== room) history.replaceState(null, '', '#' + room);
    if (stream) stream.close();
    stream = new EventSource(`/api/rooms/${room}/events?token=${token()}`);
    stream.onmessage = (event) => {
      const firstSnapshot = !view;
      const previousMoves = view ? view.moves.length : -1;
      view = JSON.parse(event.data);
      state = view.state;
      if (firstSnapshot) {
        clearInterval(lobbyTimer);
        $('lobby').hidden = true;
        $('game').hidden = false;
        $('roomCode').textContent = room;
        $('link').textContent = location.href;
      }
      // Keep the selection while nothing has moved (e.g. the opponent reconnecting).
      if (view.moves.length !== previousMoves) { selected = null; promotion = null; }
      render();
    };
    stream.onerror = () => {
      // A closed stream means the server refused us: the game no longer exists.
      if (stream && stream.readyState === EventSource.CLOSED) showLobby(`Game ${room} was not found.`);
      else if (view) $('hint').textContent = 'Connection lost. Reconnecting…';
    };
  }

  $('create').onclick = async () => {
    $('create').disabled = true;
    try {
      const res = await fetch('/api/rooms', { method: 'POST' });
      enterRoom((await res.json()).room);
    } catch {
      $('lobbyError').textContent = 'Could not reach the server.';
    }
    $('create').disabled = false;
  };

  // ---- Playing -------------------------------------------------------------

  const myTurn = () =>
    view && view.you && !view.status.over && view.players.w.taken && view.players.b.taken &&
    state === view.state && state.turn === view.you;

  // Step 2 of the remote: a destination was chosen for the selected piece.
  function choosePosition(to) {
    const chosen = Chess.legalMoves(state).filter((m) => m.from === selected && m.to === to);
    if (chosen.length === 1) return play(chosen[0]);
    promotion = { from: selected, to };   // several moves share the square: pick the new piece
    render(true);
  }

  async function play(move) {
    selected = null; promotion = null;
    state = Chess.applyMove(state, move);   // show the move at once; the server confirms it
    view.lastMove = { from: move.from, to: move.to };
    render();
    try {
      await post('move', move);
    } catch (err) {
      state = view.state;
      render();
      $('hint').textContent = err.message;
    }
  }

  $('resign').onclick = async () => {
    if (!resignArmed) {
      resignArmed = true;
      render();
      setTimeout(() => { resignArmed = false; if (view) render(); }, 4000);
      return;
    }
    resignArmed = false;
    post('resign').catch((err) => { $('hint').textContent = err.message; });
  };
  $('rematch').onclick = () => post('rematch').catch((err) => { $('hint').textContent = err.message; });
  $('leave').onclick = () => showLobby();
  $('copy').onclick = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      $('copy').textContent = 'Copied';
    } catch {
      // No clipboard access (plain http): highlight the link so it can be copied by hand.
      getSelection().selectAllChildren($('link'));
      $('copy').textContent = 'Link selected';
    }
    setTimeout(() => { $('copy').textContent = 'Copy invite link'; }, 1500);
  };

  // ---- Rendering -----------------------------------------------------------

  function pieceEl(piece) {
    const el = document.createElement('span');
    el.className = 'piece ' + Chess.colorOf(piece);
    el.textContent = glyph(piece);
    return el;
  }

  function renderBoard() {
    const flipped = view.you === 'b';
    const moves = myTurn() && selected !== null ? Chess.legalMoves(state) : [];
    const targets = new Set(moves.filter((m) => m.from === selected).map((m) => m.to));
    const checked = Chess.inCheck(state) ? Chess.kingSquare(state.board, state.turn) : -1;

    const board = $('board');
    board.textContent = '';
    for (let i = 0; i < 64; i++) {
      const sq = flipped ? 63 - i : i;
      const piece = state.board[sq];
      const name = Chess.squareName(sq);
      const el = document.createElement('div');
      el.dataset.sq = sq;
      el.setAttribute('role', 'img');
      el.className = 'sq' + (((sq >> 3) + (sq & 7)) % 2 ? ' dark' : '');
      if (view.lastMove && (view.lastMove.from === sq || view.lastMove.to === sq)) el.classList.add('last');
      if (sq === selected) el.classList.add('selected');
      if (sq === checked) el.classList.add('check');
      if (targets.has(sq)) {
        el.classList.add('target');
        if (piece || sq === state.ep) el.classList.add('capture');
      }
      let label = name + (piece ? `, ${COLOR[Chess.colorOf(piece)].toLowerCase()} ${NAME[piece.toLowerCase()]}` : '');
      if (sq === selected) label += ', selected';
      if (targets.has(sq)) label += ', possible move';
      el.setAttribute('aria-label', label);

      if (i % 8 === 0) el.append(Object.assign(document.createElement('span'), { className: 'coord rank', textContent: name[1] }));
      if (i >= 56) el.append(Object.assign(document.createElement('span'), { className: 'coord file', textContent: name[0] }));
      if (piece) el.append(pieceEl(piece));
      board.append(el);
    }
  }

  function renderPlayers() {
    const bottomColor = view.you || 'w';
    const counts = {};
    for (const piece of state.board) if (piece) counts[piece] = (counts[piece] || 0) + 1;
    const material = { w: 0, b: 0 };
    for (const type in VALUE) {
      material.w += (counts[type.toUpperCase()] || 0) * VALUE[type];
      material.b += (counts[type] || 0) * VALUE[type];
    }

    for (const [id, color] of [['bottom', bottomColor], ['top', Chess.other(bottomColor)]]) {
      const el = $(id);
      const seat = view.players[color];
      el.classList.toggle('online', seat.online);
      el.classList.toggle('turn', !view.status.over && seat.taken && state.turn === color && view.players.w.taken && view.players.b.taken);
      let name = COLOR[color];
      if (view.you === color) name += ' (you)';
      else if (!seat.taken) name += ' — waiting to join';
      else if (!seat.online) name += ' — disconnected';
      el.querySelector('.name').textContent = name;

      // Pieces this player has captured: whatever the other side is missing.
      const taken = el.querySelector('.taken');
      taken.textContent = '';
      const enemy = Chess.other(color);
      for (const type of 'qrbnp') {
        const piece = enemy === 'w' ? type.toUpperCase() : type;
        const missing = Math.max(0, START_COUNT[type] - (counts[piece] || 0));
        if (missing) taken.append(glyph(piece).repeat(missing));
      }
      const lead = material[color] - material[enemy];
      if (lead > 0) taken.append(Object.assign(document.createElement('b'), { textContent: '+' + lead }));
    }
  }

  function renderStatus() {
    const { status, you, players } = view;
    const waiting = !players.w.taken || !players.b.taken;
    let text, hint = '';
    if (status.over) {
      text = status.winner
        ? `${COLOR[status.winner]} wins by ${status.reason}.`
        : `Draw by ${status.reason}.`;
      if (you) {
        if (view.rematch[you]) hint = 'Rematch offered. Waiting for your opponent…';
        else if (view.rematch[Chess.other(you)]) hint = 'Your opponent wants a rematch.';
      }
    } else if (waiting) {
      text = 'Waiting for an opponent to join.';
      hint = `They can open this link, or press Join ${view.room} on the start page.`;
    } else if (!you) {
      text = `${COLOR[state.turn]} to move.`;
      hint = 'You are watching this game.';
    } else if (state.turn === you) {
      text = Chess.inCheck(state) ? 'You are in check.' : 'Your turn.';
      if (promotion) hint = 'Select what the pawn becomes.';
      else if (selected === null) hint = 'Select a piece.';
      else hint = `Select a position for the ${NAME[state.board[selected].toLowerCase()]} on ${Chess.squareName(selected)}.`;
    } else {
      text = `${COLOR[state.turn]} is thinking…`;
    }
    $('status').textContent = text;
    $('hint').textContent = hint;

    $('invite').hidden = !waiting;
    $('resign').hidden = !you || status.over || waiting;
    $('resign').textContent = resignArmed ? 'Tap again to resign' : 'Resign';
    $('rematch').hidden = !you || !status.over;
    $('rematch').disabled = !!you && view.rematch[you];
  }

  // The remote: every way to act on the board is a button here.
  function renderPad(refocus) {
    const pad = $('pad');
    pad.textContent = '';
    if (!myTurn()) return;
    const key = (text, piece, label, onclick, wide) => {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = 'key' + (wide ? ' wide' : '');
      if (piece) el.append(pieceEl(piece));
      el.append(text);
      el.setAttribute('aria-label', label);
      el.onclick = onclick;
      pad.append(el);
    };
    const moves = Chess.legalMoves(state);

    if (promotion) {
      for (const type of 'qrbn') {
        const piece = view.you === 'w' ? type.toUpperCase() : type;
        key('', piece, 'Promote to ' + NAME[type], () => play({ ...promotion, promo: type }));
      }
      key('Back', null, 'Back to positions', () => { promotion = null; render(true); }, true);
    } else if (selected !== null) {
      const targets = [...new Set(moves.filter((m) => m.from === selected).map((m) => m.to))];
      targets.sort((a, b) => (a & 7) - (b & 7) || b - a);
      for (const to of targets) {
        const capture = state.board[to] || to === state.ep && state.board[selected].toLowerCase() === 'p';
        const name = Chess.squareName(to);
        key((capture ? '×' : '') + name, null, (capture ? 'Capture on ' : 'Move to ') + name, () => choosePosition(to));
      }
      key('Back', null, 'Back to pieces', () => { selected = null; render(true); }, true);
    } else {
      const pieces = [...new Set(moves.map((m) => m.from))];
      const rank = (sq) => 'kqrbnp'.indexOf(state.board[sq].toLowerCase());
      pieces.sort((a, b) => rank(a) - rank(b) || (a & 7) - (b & 7) || b - a);
      for (const sq of pieces) {
        const piece = state.board[sq];
        const name = Chess.squareName(sq);
        key(name, piece, `${NAME[piece.toLowerCase()]} on ${name}`, () => { selected = sq; render(true); });
      }
    }
    if (refocus && pad.firstChild) pad.firstChild.focus();
  }

  function renderMoves() {
    const list = $('moves');
    list.textContent = '';
    view.moves.forEach((san, i) => {
      if (i % 2 === 0) list.append(Object.assign(document.createElement('li'), { className: 'n', textContent: i / 2 + 1 + '.' }));
      list.append(Object.assign(document.createElement('li'), { textContent: san }));
    });
    list.scrollTop = list.scrollHeight;
  }

  function render(refocus) {
    renderBoard();
    renderPlayers();
    renderStatus();
    renderPad(refocus);
    renderMoves();
  }

  // ---- Start ---------------------------------------------------------------

  window.addEventListener('hashchange', () => {
    const code = location.hash.slice(1);
    if (code && code.toUpperCase() !== room) enterRoom(code);
    else if (!code && room) showLobby();
  });

  if (location.hash.length > 1) enterRoom(location.hash.slice(1));
  else showLobby();
})();
