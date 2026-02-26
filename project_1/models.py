class Calculation:
    """
    Represents a calculation with an expression, result, and timestamp.

    Attributes:
        expression (str): The calculation expression.
        result (float): The result of the calculation.
        timestamp (str): The timestamp of the calculation.
    """
    def __init__(self, expression, result, timestamp):
        self.expression = expression
        self.result = result
        self.timestamp = timestamp

