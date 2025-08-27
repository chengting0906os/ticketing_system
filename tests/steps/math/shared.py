"""Shared state for math steps"""

class MathState:
    """Class to hold shared state between steps"""
    numbers = []
    result = 0
    
    @classmethod
    def reset(cls):
        cls.numbers = []
        cls.result = 0
