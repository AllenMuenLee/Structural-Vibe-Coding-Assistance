import sqlite3
from project_1.models import Calculation

def setup_database():
    """
    Set up the SQLite database and create the necessary tables.
    """
    conn = sqlite3.connect('calculation_history.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expression TEXT NOT NULL,
            result REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def insert_calculation(expression, result):
    """
    Insert a new calculation into the database.

    Args:
        expression (str): The calculation expression.
        result (float): The result of the calculation.
    """
    conn = sqlite3.connect('calculation_history.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO calculations (expression, result) VALUES (?,?)
    ''', (expression, result))
    conn.commit()
    conn.close()

def get_calculation_history():
    """
    Retrieve the calculation history from the database.

    Returns:
        list: A list of Calculation objects representing the history.
    """
    conn = sqlite3.connect('calculation_history.db')
    cursor = conn.cursor()
    cursor.execute('SELECT expression, result, timestamp FROM calculations ORDER BY timestamp DESC')
    rows = cursor.fetchall()
    conn.close()
    return [Calculation(row[0], row[1], row[2]) for row in rows]

