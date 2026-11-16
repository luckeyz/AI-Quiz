# Chess

Two-player online chess driven by a button remote. The board only displays the
game. Beside it (below it on a phone) the remote lists your movable pieces as
buttons; press one and it lists that piece's positions. There are no text
fields and nothing on the board is clickable.

## Run

```sh
cd chess
npm start            # http://localhost:3000, or PORT=8080 npm start
```

Needs Node 18 or newer and has no dependencies. Press **Create game**, then either send
your opponent the invite link or have them press **Join <code>** on the start
page, which lists every game waiting for a second player. The first two people
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
