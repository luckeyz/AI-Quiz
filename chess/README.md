# Chess

Two-player online chess. The whole interface is two taps: select a piece, then
select where it goes. Legal destinations are marked once a piece is selected.

## Run

```sh
cd chess
npm start            # http://localhost:3000, or PORT=8080 npm start
```

Needs Node 18 or newer and has no dependencies. Press **Create game**, then send
the invite link (or the five-letter code) to your opponent. The first two people
in a game play White and Black; anyone else with the link watches.

To play someone outside your network, run it on a host they can reach.

## What it does

- Full rules: castling, en passant, promotion (you pick the piece), check,
  checkmate, stalemate, and draws by threefold repetition, the fifty-move rule
  and insufficient material.
- The server checks every move, so a modified client cannot cheat.
- Reloading the page keeps your seat. A seat left empty for 20 seconds can be
  taken by the next person to open the link.
- Resign, and rematch with colours swapped.

Games live in server memory: restarting the server ends them.

## Layout

- `public/engine.js` – the rules, used by both the server and the browser
- `server.js` – rooms, seats and move validation over HTTP + server-sent events
- `public/index.html`, `public/app.js` – the interface
- `test/engine.test.js` – rule tests (`npm test`), including perft move counts
