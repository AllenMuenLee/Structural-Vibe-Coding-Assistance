document.addEventListener('DOMContentLoaded', () => {
    const cells = document.querySelectorAll('.cell');
    const status = document.getElementById('status');
    const resetButton = document.getElementById('reset-button');
    let currentPlayer = 'X';
    let gameBoard = Array(9).fill(null);

    const winLines = [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [0, 3, 6],
        [1, 4, 7],
        [2, 5, 8],
        [0, 4, 8],
        [2, 4, 6]
    ];

    function handleCellClick(event) {
        const cell = event.target;
        const index = cell.getAttribute('data-index');

        if (gameBoard[index] || calculateWinner(gameBoard)) {
            return;
        }

        gameBoard[index] = currentPlayer;
        cell.textContent = currentPlayer;

        const winner = calculateWinner(gameBoard);
        if (winner) {
            status.textContent = `Player ${winner} wins!`;
        } else if (gameBoard.every(cell => cell)) {
            status.textContent = "It's a draw!";
        } else {
            currentPlayer = currentPlayer === 'X'? 'O' : 'X';
            status.textContent = `Next player: ${currentPlayer}`;
        }
    }

    function handleReset() {
        gameBoard.fill(null);
        cells.forEach(cell => cell.textContent = '');
        currentPlayer = 'X';
        status.textContent = `Next player: ${currentPlayer}`;
    }

    function calculateWinner(board) {
        for (let line of winLines) {
            const [a, b, c] = line;
            if (board[a] && board[a] === board[b] && board[a] === board[c]) {
                return board[a];
            }
        }
        return null;
    }

    cells.forEach(cell => cell.addEventListener('click', handleCellClick));
    resetButton.addEventListener('click', handleReset);
});
