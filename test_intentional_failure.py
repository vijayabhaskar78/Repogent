#!/usr/bin/env python3
"""
Intentional test failure to trigger CI/CD Agent
This file is for testing purposes only - delete after testing
"""
import unittest


class TestIntentionalFailure(unittest.TestCase):
    """Test case that will fail to trigger CI/CD monitoring"""
    
    def test_this_should_fail(self):
        """This test intentionally fails to test CI/CD Agent"""
        # This assertion will fail
        self.assertEqual(1, 2, "Intentional failure: 1 does not equal 2")
    
    def test_another_failure(self):
        """Another failing test with different error"""
        # This will raise an exception
        result = 10 / 0  # ZeroDivisionError


if __name__ == '__main__':
    unittest.main()
