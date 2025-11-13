#!/usr/bin/env python3
"""
Demo file to test CI/CD monitoring - contains intentional syntax error
"""

def calculate_sum(a, b):
    """Calculate sum of two numbers"""
    return a + b


def process_data(data):
    """Process data - INTENTIONAL SYNTAX ERROR BELOW"""
    result = []
    for item in data:
        result.append(item * 2)
    # Missing colon will cause syntax error
    if len(result) > 0
        print("Processing complete")  # Syntax error: missing colon above
    return result


if __name__ == "__main__":
    print("Testing CI/CD Agent")
    data = [1, 2, 3, 4, 5]
    result = process_data(data)
    print(f"Result: {result}")
