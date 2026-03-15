/**
 * Represents the game board for Tic-Tac-Toe.
 * @class
 */
class GameBoard {
    /**
     * Creates an instance of GameBoard.
     */
    constructor() {
        this.board = Array(9).fill(null);
    }

    /**
     * Checks if the board is full.
     * @returns {boolean} True if the board is full, otherwise false.
     */
    isFull() {
        return this.board.every(cell => cell!== null);
    }

    /**
     * Checks if there is a winner.
     * @returns {string|null} The winner ('X' or 'O') or null if no winner.
     */
    checkWinner() {
        const lines = [
            [0, 1, 2],
            [3, 4, 5],
            [6, 7, 8],
            [0, 3, 6],
            [1, 4, 7],
            [2, 5, 8],
            [0, 4, 8],
            [2, 4, 6]
        ];

        for (let line of lines) {
            const [a, b, c] = line;
            if (this.board[a] && this.board[a] === this.board[b] && this.board[a] === this.board[c]) {
                return this.board[a];
            }
        }

        return null;
    }

    /**
     * Places a mark on the board.
     * @param {number} index - The index of the cell to place the mark.
     * @param {string} mark - The mark to place ('X' or 'O').
     */
    placeMark(index, mark) {
        if (this.board[index] === null) {
            this.board[index] = mark;
        }
    }

    /**
     * Resets the board to its initial state.
     */
    reset() {
        this.board = Array(9).fill(null);
    }
}

/**
 * Manages the game state and logic for Tic-Tac-Toe.
 * @class
 */
class Game {
    /**
     * Creates an instance of Game.
     */
    constructor() {
        this.board = new GameBoard();
        this.currentPlayer = 'X';
    }

    /**
     * Switches the current player.
     */
    switchPlayer() {
        this.currentPlayer = this.currentPlayer === 'X'? 'O' : 'X';
    }

    /**
     * Makes a move on the board.
     * @param {number} index - The index of the cell to place the mark.
     * @returns {boolean} True if the move was successful, otherwise false.
     */
    makeMove(index) {
        if (this.board.board[index] === null) {
            this.board.placeMark(index, this.currentPlayer);
            this.switchPlayer();
            return true;
        }
        return false;
    }

    /**
     * Checks if the game is over.
     * @returns {string|null} The winner ('X' or 'O') or null if no winner.
     */
    isGameOver() {
        const winner = this.board.checkWinner();
        if (winner) {
            return winner;
        }
        if (this.board.isFull()) {
            return 'Draw';
        }
        return null;
    }

    /**
     * Resets the game to its initial state.
     */
    reset() {
        this.board.reset();
        this.currentPlayer = 'X';
    }
}
