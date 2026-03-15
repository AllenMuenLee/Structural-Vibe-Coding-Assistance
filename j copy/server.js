const express = require('express');
const app = express();
const port = 3000;
const Game = require('./gameLogic').Game;

/**
 * Setup a simple Express server.
 */
app.get('/', (req, res) => {
  res.send('Hello World!');
});

/**
 * Handles GET request to start a new game.
 */
app.get('/start', (req, res) => {
  const game = new Game();
  res.json({ status: 'Game started', gameState: game });
});

/**
 * Handles POST request to make a move in the game.
 */
app.post('/move/:index', (req, res) => {
  const index = parseInt(req.params.index);
  const game = new Game(); // In a real application, you would maintain game state across requests
  const moveSuccess = game.makeMove(index);
  if (moveSuccess) {
    res.json({ status: 'Move made', gameState: game });
  } else {
    res.status(400).json({ status: 'Invalid move' });
  }
});

/**
 * Handles GET request to check the game status.
 */
app.get('/status', (req, res) => {
  const game = new Game(); // In a real application, you would maintain game state across requests
  const gameOver = game.isGameOver();
  if (gameOver) {
    res.json({ status: 'Game over', winner: gameOver });
  } else {
    res.json({ status: 'Game in progress', currentPlayer: game.currentPlayer });
  }
});

app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}/`);
});
