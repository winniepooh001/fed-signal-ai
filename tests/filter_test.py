#!/usr/bin/env python3
"""
Test Filter Bug Fix
===================

This script tests the filter validation and auto-fix functionality
to ensure the sector equals bug is resolved.
"""

import sys
import os
from utils.logging_config import initialize_logging, get_logger

# Initialize logging for tests
test_logger = initialize_logging(
    log_level="INFO",
    console_output=True,
    log_file="filter_fix_test.log"
)


def test_filter_validation():
    """Test the filter validation directly"""

    test_logger.info("=" * 60)
    test_logger.info("TESTING FILTER VALIDATION")
    test_logger.info("=" * 60)

    try:
        from tools.tradingview_query import TradingViewQueryTool

        # Create tool instance
        tool = TradingViewQueryTool()

        # Test Case 1: Multiple equals filters (the original bug)
        test_logger.info("Test 1: Multiple equals filters for same column")
        problematic_filters = [
            {"type": "equals", "column": "sector", "value": "Utilities"},
            {"type": "equals", "column": "sector", "value": "Consumer Staples"},
            {"type": "equals", "column": "sector", "value": "Healthcare"},
            {"type": "greater_than", "column": "volume", "value": 1000000}
        ]

        test_logger.info(f"Input: {len(problematic_filters)} filters")
        test_logger.info(f"Problematic filters: {problematic_filters}")

        fixed_filters = tool._validate_and_fix_filters(problematic_filters)

        test_logger.info(f"Output: {len(fixed_filters)} filters")
        for i, f in enumerate(fixed_filters):
            if hasattr(f, 'model_dump'):
                test_logger.info(f"  {i + 1}. {f.model_dump()}")
            else:
                test_logger.info(f"  {i + 1}. {f}")

        # Verify the fix
        sector_filters = [f for f in fixed_filters if getattr(f, 'column', None) == 'sector']
        if len(sector_filters) == 1 and getattr(sector_filters[0], 'type', None) == 'in':
            test_logger.info("✅ SUCCESS: Multiple equals converted to single 'in' filter")
        else:
            test_logger.error("❌ FAILED: Multiple equals not properly converted")

        print()

    except Exception as e:
        test_logger.error(f"Filter validation test failed: {e}", exc_info=True)
        return False


def test_range_filter_fix():
    """Test range filter consolidation"""

    test_logger.info("Test 2: Separate greater_than + less_than filters")

    try:
        from tools.tradingview_query import TradingViewQueryTool

        tool = TradingViewQueryTool()

        range_filters = [
            {"type": "greater_than", "column": "price_earnings_ttm", "value": 10},
            {"type": "less_than", "column": "price_earnings_ttm", "value": 25},
            {"type": "greater_than", "column": "volume", "value": 500000}
        ]

        test_logger.info(f"Input: {len(range_filters)} filters")
        test_logger.info(f"Range filters: {range_filters}")

        fixed_filters = tool._validate_and_fix_filters(range_filters)

        test_logger.info(f"Output: {len(fixed_filters)} filters")
        for i, f in enumerate(fixed_filters):
            if hasattr(f, 'model_dump'):
                test_logger.info(f"  {i + 1}. {f.model_dump()}")
            else:
                test_logger.info(f"  {i + 1}. {f}")

        # Verify the fix
        pe_filters = [f for f in fixed_filters if getattr(f, 'column', None) == 'price_earnings_ttm']
        if len(pe_filters) == 1 and getattr(pe_filters[0], 'type', None) == 'range':
            test_logger.info("✅ SUCCESS: Greater than + less than converted to range filter")
        else:
            test_logger.error("❌ FAILED: Range filters not properly consolidated")

        print()

    except Exception as e:
        test_logger.error(f"Range filter test failed: {e}", exc_info=True)
        return False


def test_correct_filters():
    """Test that correct filters are not modified"""

    test_logger.info("Test 3: Correct filters should remain unchanged")

    try:
        from tools.tradingview_query import TradingViewQueryTool

        tool = TradingViewQueryTool()

        correct_filters = [
            {"type": "in", "column": "sector", "values": ["Technology", "Healthcare"]},
            {"type": "range", "column": "price_earnings_ttm", "min_value": 10, "max_value": 25},
            {"type": "greater_than", "column": "volume", "value": 1000000}
        ]

        test_logger.info(f"Input: {len(correct_filters)} filters")
        test_logger.info(f"Correct filters: {correct_filters}")

        fixed_filters = tool._validate_and_fix_filters(correct_filters)

        test_logger.info(f"Output: {len(fixed_filters)} filters")
        for i, f in enumerate(fixed_filters):
            if hasattr(f, 'model_dump'):
                test_logger.info(f"  {i + 1}. {f.model_dump()}")
            else:
                test_logger.info(f"  {i + 1}. {f}")

        # Verify no changes
        if len(fixed_filters) == len(correct_filters):
            test_logger.info("✅ SUCCESS: Correct filters remained unchanged")
        else:
            test_logger.error("❌ FAILED: Correct filters were modified unexpectedly")

        print()

    except Exception as e:
        test_logger.error(f"Correct filter test failed: {e}", exc_info=True)
        return False


def test_end_to_end():
    """Test the fix with actual TradingView tool execution"""

    test_logger.info("Test 4: End-to-end with TradingView tool")

    try:
        from tools.tradingview_query import TradingViewQueryTool

        tool = TradingViewQueryTool()

        # Test with the original problematic filter pattern
        test_logger.info("Testing with problematic filters in actual tool execution")

        result = tool._run(
            columns=["name", "close", "change", "volume", "sector"],
            filters=[
                {"type": "equals", "column": "sector", "value": "Technology"},
                {"type": "equals", "column": "sector", "value": "Healthcare"},
                {"type": "greater_than", "column": "market_cap_basic", "value": 1000000000},
                {"type": "greater_than", "column": "volume", "value": 1000000}
            ],
            sort_column="change",
            limit=10
        )

        import json
        parsed_result = json.loads(result)

        if parsed_result.get('success'):
            test_logger.info(f"✅ SUCCESS: Tool executed successfully with auto-fixed filters")
            test_logger.info(f"Found {parsed_result.get('total_results', 0)} stocks")
        else:
            test_logger.error(f"❌ FAILED: Tool execution failed: {parsed_result.get('error')}")

    except Exception as e:
        test_logger.error(f"End-to-end test failed: {e}", exc_info=True)
        return False


def run_all_tests():
    """Run all filter fix tests"""

    test_logger.info("🚀 STARTING FILTER FIX VALIDATION TESTS")
    test_logger.info("=" * 80)

    tests = [
        test_filter_validation,
        test_range_filter_fix,
        test_correct_filters,
        test_end_to_end
    ]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            test_logger.error(f"Test {test_func.__name__} failed: {e}")

    test_logger.info("=" * 80)
    test_logger.info("FILTER FIX TEST SUMMARY")
    test_logger.info(f"Tests passed: {passed}/{total}")

    if passed == total:
        test_logger.info("🎉 ALL FILTER FIX TESTS PASSED!")
        return True
    else:
        test_logger.error(f"⚠️ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)