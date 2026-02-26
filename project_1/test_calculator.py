import unittest
from calculator import Calculator

class TestCalculator(unittest.TestCase):
    """
    Test cases for the Calculator class.
    """
    
    def test_addition(self):
        """
        Test the addition method of the Calculator class.
        """
        calc = Calculator()
        self.assertEqual(calc.add(2, 3), 5)
        self.assertEqual(calc.add(-1, 1), 0)
        self.assertEqual(calc.add(-1, -1), -2)
    
    def test_subtraction(self):
        """
        Test the subtraction method of the Calculator class.
        """
        calc = Calculator()
        self.assertEqual(calc.subtract(3, 2), 1)
        self.assertEqual(calc.subtract(-1, 1), -2)
        self.assertEqual(calc.subtract(-1, -1), 0)
    
    def test_multiplication(self):
        """
        Test the multiplication method of the Calculator class.
        """
        calc = Calculator()
        self.assertEqual(calc.multiply(2, 3), 6)
        self.assertEqual(calc.multiply(-1, 1), -1)
        self.assertEqual(calc.multiply(-1, -1), 1)
    
    def test_division(self):
        """
        Test the division method of the Calculator class.
        """
        calc = Calculator()
        self.assertEqual(calc.divide(6, 3), 2)
        self.assertEqual(calc.divide(-1, 1), -1)
        self.assertEqual(calc.divide(-1, -1), 1)
        with self.assertRaises(ValueError):
            calc.divide(1, 0)

if __name__ == '__main__':
    unittest.main()

