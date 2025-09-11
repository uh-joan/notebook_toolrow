#!/usr/bin/env python3
"""
Test runner for the reasoning system.

Runs all tests and provides a summary of results.
"""

import sys
import asyncio
import pytest
from pathlib import Path

# Add the parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def run_all_tests():
    """Run all reasoning system tests."""
    test_directory = Path(__file__).parent
    
    # Configure pytest arguments
    pytest_args = [
        str(test_directory),
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "--strict-markers",  # Strict marker checking
        "-x",  # Stop on first failure (remove this for full test runs)
    ]
    
    print("🧪 Running Reasoning System Tests")
    print("=" * 50)
    
    # Run tests
    exit_code = pytest.main(pytest_args)
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code: {exit_code}")
    
    return exit_code


def run_specific_test_suite(suite_name: str):
    """Run a specific test suite."""
    test_file = Path(__file__).parent / f"test_{suite_name}.py"
    
    if not test_file.exists():
        print(f"❌ Test suite not found: {test_file}")
        return 1
    
    print(f"🧪 Running {suite_name} tests")
    print("=" * 30)
    
    exit_code = pytest.main([str(test_file), "-v"])
    
    if exit_code == 0:
        print(f"\n✅ {suite_name} tests passed!")
    else:
        print(f"\n❌ {suite_name} tests failed!")
    
    return exit_code


def main():
    """Main test runner."""
    if len(sys.argv) > 1:
        suite_name = sys.argv[1]
        exit_code = run_specific_test_suite(suite_name)
    else:
        exit_code = run_all_tests()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
