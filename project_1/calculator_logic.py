# Imports
import operator

# Functions and Imports from symbol table: None

def add(x, y):
    """
    Add two numbers together.

    Args:
    x (float): The first number.
    y (float): The second number.

    Returns:
    float: The sum of x and y.
    """
    return operator.add(x, y)

def subtract(x, y):
    """
    Subtract the second number from the first number.

    Args:
    x (float): The first number.
    y (float): The second number.

    Returns:
    float: The result of x minus y.
    """
    return operator.sub(x, y)

def multiply(x, y):
    """
    Multiply two numbers.

    Args:
    x (float): The first number.
    y (float): The second number.

    Returns:
    float: The product of x and y.
    """
    return operator.mul(x, y)

def divide(x, y):
    """
    Divide the first number by the second number.

    Args:
    x (float): The first number.
    y (float): The second number.

    Returns:
    float: The result of x divided by y.
    """
    if y == 0:
        raise ValueError("Cannot divide by zero")
    return operator.truediv(x, y)

