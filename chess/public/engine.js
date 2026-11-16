// Chess rules, shared by the server (authoritative) and the browser (move hints).
// Squares are 0..63 with 0 = a8 and 63 = h1. Pieces are FEN letters; null is empty.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Chess = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

  const KNIGHT = [[-2, -1], [-2, 1], [-1, -2], [-1, 2], [1, -2], [1, 2], [2, -1], [2, 1]];
  const DIAG = [[-1, -1], [-1, 1], [1, -1], [1, 1]];
  const ORTH = [[-1, 0], [1, 0], [0, -1], [0, 1]];
  const ALL = DIAG.concat(ORTH);

  const colorOf = (p) => (p ? (p === p.toUpperCase() ? 'w' : 'b') : null);
  const other = (c) => (c === 'w' ? 'b' : 'w');
  const squareName = (sq) => 'abcdefgh'[sq & 7] + (8 - (sq >> 3));

  function fromFen(fen) {
    const [rows, turn, castling, ep, half, full] = fen.trim().split(/\s+/);
    const board = [];
    for (const ch of rows.replace(/\//g, '')) {
      if (ch >= '1' && ch <= '8') for (let i = 0; i < +ch; i++) board.push(null);
      else board.push(ch);
    }
    if (board.length !== 64) throw new Error('Bad FEN: ' + fen);
    return {
      board,
      turn: turn || 'w',
      castling: !castling || castling === '-' ? '' : castling,
      ep: !ep || ep === '-' ? null : 'abcdefgh'.indexOf(ep[0]) + (8 - +ep[1]) * 8,
      halfmove: +half || 0,
      fullmove: +full || 1,
    };
  }

  function boardKey(board) {
    let out = '';
    for (let r = 0; r < 8; r++) {
      let empty = 0;
      for (let c = 0; c < 8; c++) {
        const p = board[r * 8 + c];
        if (!p) { empty++; continue; }
        if (empty) { out += empty; empty = 0; }
        out += p;
      }
      if (empty) out += empty;
      if (r < 7) out += '/';
    }
    return out;
  }

  // Identifies a position for the threefold-repetition rule.
  function positionKey(s) {
    return [boardKey(s.board), s.turn, s.castling || '-', s.ep === null ? '-' : squareName(s.ep)].join(' ');
  }

  const toFen = (s) => positionKey(s) + ' ' + s.halfmove + ' ' + s.fullmove;
  const newGame = () => fromFen(START_FEN);

  function attacked(board, sq, by) {
    const r = sq >> 3, c = sq & 7;
    const white = by === 'w';
    const pawn = white ? 'P' : 'p', knight = white ? 'N' : 'n', king = white ? 'K' : 'k';
    const bishop = white ? 'B' : 'b', rook = white ? 'R' : 'r', queen = white ? 'Q' : 'q';

    const pr = r + (white ? 1 : -1);
    if (pr >= 0 && pr < 8) {
      if (c > 0 && board[pr * 8 + c - 1] === pawn) return true;
      if (c < 7 && board[pr * 8 + c + 1] === pawn) return true;
    }
    for (const [dr, dc] of KNIGHT) {
      const nr = r + dr, nc = c + dc;
      if (nr >= 0 && nr < 8 && nc >= 0 && nc < 8 && board[nr * 8 + nc] === knight) return true;
    }
    for (const [dr, dc] of ALL) {
      const nr = r + dr, nc = c + dc;
      if (nr >= 0 && nr < 8 && nc >= 0 && nc < 8 && board[nr * 8 + nc] === king) return true;
    }
    const ray = (dirs, slider) => {
      for (const [dr, dc] of dirs) {
        let nr = r + dr, nc = c + dc;
        while (nr >= 0 && nr < 8 && nc >= 0 && nc < 8) {
          const p = board[nr * 8 + nc];
          if (p) {
            if (p === slider || p === queen) return true;
            break;
          }
          nr += dr; nc += dc;
        }
      }
      return false;
    };
    return ray(DIAG, bishop) || ray(ORTH, rook);
  }

  function kingSquare(board, color) {
    return board.indexOf(color === 'w' ? 'K' : 'k');
  }

  function inCheck(s) {
    return attacked(s.board, kingSquare(s.board, s.turn), other(s.turn));
  }

  function pseudoMoves(s) {
    const { board, turn } = s;
    const white = turn === 'w';
    const moves = [];
    for (let from = 0; from < 64; from++) {
      const p = board[from];
      if (!p || colorOf(p) !== turn) continue;
      const r = from >> 3, c = from & 7;
      const type = p.toLowerCase();

      if (type === 'p') {
        const dir = white ? -1 : 1;
        const nr = r + dir;
        if (nr < 0 || nr > 7) continue;
        const add = (to) => {
          if (nr === 0 || nr === 7) for (const promo of 'qrbn') moves.push({ from, to, promo });
          else moves.push({ from, to });
        };
        if (!board[nr * 8 + c]) {
          add(nr * 8 + c);
          if (r === (white ? 6 : 1) && !board[(r + 2 * dir) * 8 + c]) moves.push({ from, to: (r + 2 * dir) * 8 + c });
        }
        for (const dc of [-1, 1]) {
          const nc = c + dc;
          if (nc < 0 || nc > 7) continue;
          const to = nr * 8 + nc;
          const target = board[to];
          if ((target && colorOf(target) !== turn) || to === s.ep) add(to);
        }
        continue;
      }

      const step = (dirs, slide) => {
        for (const [dr, dc] of dirs) {
          let nr = r + dr, nc = c + dc;
          while (nr >= 0 && nr < 8 && nc >= 0 && nc < 8) {
            const target = board[nr * 8 + nc];
            if (!target) moves.push({ from, to: nr * 8 + nc });
            else {
              if (colorOf(target) !== turn) moves.push({ from, to: nr * 8 + nc });
              break;
            }
            if (!slide) break;
            nr += dr; nc += dc;
          }
        }
      };
      if (type === 'n') step(KNIGHT, false);
      else if (type === 'b') step(DIAG, true);
      else if (type === 'r') step(ORTH, true);
      else if (type === 'q') step(ALL, true);
      else if (type === 'k') {
        step(ALL, false);
        const home = white ? 60 : 4;
        const enemy = other(turn);
        const rook = white ? 'R' : 'r';
        if (from === home && !attacked(board, home, enemy)) {
          if (s.castling.includes(white ? 'K' : 'k') && board[home + 3] === rook &&
              !board[home + 1] && !board[home + 2] &&
              !attacked(board, home + 1, enemy) && !attacked(board, home + 2, enemy)) {
            moves.push({ from, to: home + 2 });
          }
          if (s.castling.includes(white ? 'Q' : 'q') && board[home - 4] === rook &&
              !board[home - 1] && !board[home - 2] && !board[home - 3] &&
              !attacked(board, home - 1, enemy) && !attacked(board, home - 2, enemy)) {
            moves.push({ from, to: home - 2 });
          }
        }
      }
    }
    return moves;
  }

  // Applies a move without checking legality. Castling, en passant and promotion
  // are inferred from the board, so a move only needs {from, to, promo?}.
  function applyMove(s, m) {
    const board = s.board.slice();
    const p = board[m.from];
    const type = p.toLowerCase();
    const white = s.turn === 'w';
    const captured = board[m.to];
    board[m.to] = p;
    board[m.from] = null;
    let ep = null;

    if (type === 'p') {
      if (m.to === s.ep) board[m.to + (white ? 8 : -8)] = null;
      if (Math.abs(m.to - m.from) === 16) {
        // Only record the en passant square when a capture is actually possible,
        // so that repetition detection compares like with like.
        const enemyPawn = white ? 'p' : 'P';
        const c = m.to & 7;
        if ((c > 0 && board[m.to - 1] === enemyPawn) || (c < 7 && board[m.to + 1] === enemyPawn)) {
          ep = (m.from + m.to) / 2;
        }
      }
      const row = m.to >> 3;
      if (row === 0 || row === 7) {
        const promo = m.promo || 'q';
        board[m.to] = white ? promo.toUpperCase() : promo.toLowerCase();
      }
    }
    if (type === 'k' && Math.abs(m.to - m.from) === 2) {
      if (m.to > m.from) { board[m.to - 1] = board[m.to + 1]; board[m.to + 1] = null; }
      else { board[m.to + 1] = board[m.to - 2]; board[m.to - 2] = null; }
    }

    let castling = s.castling;
    const drop = (chars) => { castling = castling.replace(new RegExp('[' + chars + ']', 'g'), ''); };
    if (type === 'k') drop(white ? 'KQ' : 'kq');
    for (const sq of [m.from, m.to]) {
      if (sq === 63) drop('K');
      else if (sq === 56) drop('Q');
      else if (sq === 7) drop('k');
      else if (sq === 0) drop('q');
    }

    return {
      board,
      turn: other(s.turn),
      castling,
      ep,
      halfmove: type === 'p' || captured ? 0 : s.halfmove + 1,
      fullmove: s.fullmove + (white ? 0 : 1),
    };
  }

  function legalMoves(s) {
    const enemy = other(s.turn);
    return pseudoMoves(s).filter((m) => {
      const next = applyMove(s, m);
      return !attacked(next.board, kingSquare(next.board, s.turn), enemy);
    });
  }

  function insufficientMaterial(board) {
    const bishopShades = new Set();
    let knights = 0;
    for (let sq = 0; sq < 64; sq++) {
      const p = board[sq];
      if (!p) continue;
      const type = p.toLowerCase();
      if (type === 'k') continue;
      if (type === 'n') knights++;
      else if (type === 'b') bishopShades.add(((sq >> 3) + (sq & 7)) % 2);
      else return false;
    }
    if (knights === 0) return bishopShades.size <= 1;
    return knights === 1 && bishopShades.size === 0;
  }

  // `repetitions` is how many times the current position has occurred so far.
  function status(s, repetitions) {
    const check = inCheck(s);
    if (!legalMoves(s).length) {
      return check
        ? { over: true, check, reason: 'checkmate', winner: other(s.turn) }
        : { over: true, check, reason: 'stalemate', winner: null };
    }
    let reason = null;
    if (insufficientMaterial(s.board)) reason = 'insufficient material';
    else if (s.halfmove >= 100) reason = 'fifty-move rule';
    else if (repetitions >= 3) reason = 'threefold repetition';
    return reason ? { over: true, check, reason, winner: null } : { over: false, check };
  }

  // Standard algebraic notation for a legal move in position `s`.
  function san(s, m) {
    const p = s.board[m.from];
    const type = p.toLowerCase();
    const capture = !!s.board[m.to] || (type === 'p' && m.to === s.ep);
    const from = squareName(m.from), to = squareName(m.to);
    let out;
    if (type === 'k' && Math.abs(m.to - m.from) === 2) {
      out = m.to > m.from ? 'O-O' : 'O-O-O';
    } else if (type === 'p') {
      out = (capture ? from[0] + 'x' : '') + to + (m.promo ? '=' + m.promo.toUpperCase() : '');
    } else {
      const rivals = legalMoves(s).filter((o) => o.to === m.to && o.from !== m.from && s.board[o.from] === p);
      let hint = '';
      if (rivals.length) {
        if (!rivals.some((o) => (o.from & 7) === (m.from & 7))) hint = from[0];
        else if (!rivals.some((o) => (o.from >> 3) === (m.from >> 3))) hint = from[1];
        else hint = from;
      }
      out = type.toUpperCase() + hint + (capture ? 'x' : '') + to;
    }
    const next = applyMove(s, m);
    if (inCheck(next)) out += legalMoves(next).length ? '+' : '#';
    return out;
  }

  return {
    START_FEN, newGame, fromFen, toFen, positionKey, squareName, colorOf, other,
    legalMoves, applyMove, inCheck, kingSquare, status, san,
  };
});
