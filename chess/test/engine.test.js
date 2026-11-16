const test = require('node:test');
const assert = require('node:assert');
const Chess = require('../public/engine.js');

function perft(state, depth) {
  const moves = Chess.legalMoves(state);
  if (depth === 1) return moves.length;
  let nodes = 0;
  for (const move of moves) nodes += perft(Chess.applyMove(state, move), depth - 1);
  return nodes;
}

const sq = (name) => 'abcdefgh'.indexOf(name[0]) + (8 - +name[1]) * 8;

function play(sans) {
  let state = Chess.newGame();
  for (const wanted of sans) {
    const move = Chess.legalMoves(state).find((m) => Chess.san(state, m) === wanted);
    assert.ok(move, `no legal move ${wanted}`);
    state = Chess.applyMove(state, move);
  }
  return state;
}

// Reference node counts from the Chess Programming Wiki's perft results.
test('perft: starting position', () => {
  assert.strictEqual(perft(Chess.newGame(), 4), 197281);
});
test('perft: castling, pins and checks (Kiwipete)', () => {
  assert.strictEqual(perft(Chess.fromFen('r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1'), 3), 97862);
});
test('perft: en passant edge cases', () => {
  assert.strictEqual(perft(Chess.fromFen('8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1'), 4), 43238);
});
test('perft: promotions', () => {
  assert.strictEqual(perft(Chess.fromFen('r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1'), 3), 9467);
});

test('checkmate is detected', () => {
  const state = play(['f3', 'e5', 'g4', 'Qh4#']);
  assert.deepStrictEqual(Chess.status(state, 1), { over: true, check: true, reason: 'checkmate', winner: 'b' });
});

test('stalemate is a draw', () => {
  const status = Chess.status(Chess.fromFen('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1'), 1);
  assert.strictEqual(status.reason, 'stalemate');
  assert.strictEqual(status.winner, null);
});

test('draws by material, fifty moves and repetition', () => {
  assert.strictEqual(Chess.status(Chess.fromFen('8/8/4k3/8/8/3KB3/8/8 w - - 0 1'), 1).reason, 'insufficient material');
  assert.strictEqual(Chess.status(Chess.fromFen('8/8/4k3/8/8/3KR3/8/8 w - - 100 80'), 1).reason, 'fifty-move rule');
  assert.strictEqual(Chess.status(Chess.newGame(), 3).reason, 'threefold repetition');
  assert.strictEqual(Chess.status(Chess.newGame(), 2).over, false);
});

test('castling moves the rook and clears the rights', () => {
  const state = play(['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5', 'O-O']);
  assert.strictEqual(state.board[sq('g1')], 'K');
  assert.strictEqual(state.board[sq('f1')], 'R');
  assert.strictEqual(state.board[sq('h1')], null);
  assert.strictEqual(state.castling, 'kq');
});

test('en passant removes the captured pawn', () => {
  const state = play(['e4', 'a6', 'e5', 'd5', 'exd6']);
  assert.strictEqual(state.board[sq('d6')], 'P');
  assert.strictEqual(state.board[sq('d5')], null);
});

test('promotion and notation', () => {
  const state = Chess.fromFen('3r2k1/4P3/8/8/8/8/8/R3K2R w KQ - 0 1');
  const sans = Chess.legalMoves(state).map((m) => Chess.san(state, m));
  for (const wanted of ['e8=Q+', 'exd8=N', 'O-O', 'Rd1']) {
    assert.ok(sans.includes(wanted), `${wanted} missing from ${sans}`);
  }
  // The black rook covers d1, so the king may not castle through it.
  assert.ok(!sans.includes('O-O-O'));
  const promoted = Chess.applyMove(state, { from: sq('e7'), to: sq('d8'), promo: 'n' });
  assert.strictEqual(promoted.board[sq('d8')], 'N');
});

test('notation disambiguates pieces that share a target', () => {
  const state = play(['Nf3', 'a6', 'd3', 'a5']);
  const sans = Chess.legalMoves(state).map((m) => Chess.san(state, m));
  assert.ok(sans.includes('Nbd2') && sans.includes('Nfd2'), String(sans));
});

test('FEN round-trips', () => {
  assert.strictEqual(Chess.toFen(Chess.newGame()), Chess.START_FEN);
});
