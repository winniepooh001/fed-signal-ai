import sys
import os

sys.path.append('..')


def debug_ticker_issue():
    """Debug where 'ticker' is coming from in the tool"""

    print("=== Debugging Ticker Field Issue ===\n")

    from tools.tradingview_query import TradingViewQueryTool
    import json

    # Create tool instance
    tool = TradingViewQueryTool()

    # Test 1: Verify exact columns being passed
    print("1. Testing exact column specification:")

    columns = ["name", "close", "change", "volume", "market_cap_basic"]
    filters = [{"type": "greater_than", "column": "change", "value": 3.0}]

    print(f"   Input columns: {columns}")
    print(f"   Input filters: {filters}")

    # Check if tool modifies columns
    print(f"\n2. Checking if tool modifies inputs...")

    try:
        # Let's intercept what gets passed to the Query
        from tradingview_screener import Query, col

        # Manual test with exact same inputs
        print("   Manual query test:")
        query = Query()
        query = query.select(*columns)
        print(f"   ✓ Manual select() worked with columns: {columns}")

        # Test each condition individually
        conditions = [
            col('exchange') != 'OTC',
            col('market_cap_basic') > 5000000000,
            col('volume') > 1000000,
            col('close') > 10,
            col('close') < 1000,
            col('relative_volume_10d_calc') > 0.3,
            col('change') > 3.0
        ]

        print(f"   Testing individual conditions:")
        for i, condition in enumerate(conditions):
            try:
                test_query = Query().select('name', 'close').where(condition).limit(1)
                _, _ = test_query.get_scanner_data()
                print(f"   ✓ Condition {i + 1} works: {condition}")
            except Exception as e:
                print(f"   ❌ Condition {i + 1} fails: {condition} - Error: {e}")

        # Test all conditions together
        print(f"\n   Testing all conditions together:")
        try:
            test_query = Query().select(*columns).where(*conditions).limit(1)
            _, df = test_query.get_scanner_data()
            print(f"   ✓ All conditions work together - got {len(df)} results")
        except Exception as e:
            print(f"   ❌ All conditions together fail: {e}")
            # Check if error mentions ticker
            if 'ticker' in str(e).lower():
                print(f"   🔍 ERROR CONTAINS 'TICKER' - this is the issue!")

    except Exception as e:
        print(f"   ❌ Manual test failed: {e}")

    # Test 3: Check if tool code has 'ticker' anywhere
    print(f"\n3. Checking tool source code for 'ticker'...")

    import inspect
    tool_source = inspect.getsource(TradingViewQueryTool)

    if 'ticker' in tool_source.lower():
        print(f"   ⚠️  Found 'ticker' in tool source code!")
        lines = tool_source.split('\n')
        for i, line in enumerate(lines):
            if 'ticker' in line.lower():
                print(f"   Line {i + 1}: {line.strip()}")
    else:
        print(f"   ✓ No 'ticker' found in tool source code")

    # Test 4: Test the tool with minimal inputs
    print(f"\n4. Testing tool with minimal safe inputs:")

    try:
        # Use only guaranteed safe columns
        safe_columns = ["name", "close"]
        safe_filters = []  # No filters first

        print(f"   Testing with safe columns only: {safe_columns}")

        result_json = tool._run(
            columns=safe_columns,
            filters=safe_filters,
            sort_column="close",
            limit=5
        )

        result = json.loads(result_json)
        if result['success']:
            print(f"   ✓ Safe columns work - got {result['total_results']} total results")
        else:
            print(f"   ❌ Even safe columns fail: {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"   ❌ Tool test failed: {e}")
        if 'ticker' in str(e).lower():
            print(f"   🔍 ERROR CONTAINS 'TICKER' - the issue is in the tool!")


def debug_columns_step_by_step():
    """Test each column individually to find the problematic one"""

    print("\n=== Testing Each Column Individually ===\n")

    from tradingview_screener import Query

    test_columns = [
        "name",
        "close",
        "change",
        "volume",
        "market_cap_basic",
        "relative_volume_10d_calc",
        "price_earnings_ttm",
        "Perf.Y"
    ]

    working_columns = []
    problematic_columns = []

    for column in test_columns:
        try:
            print(f"Testing column: '{column}'")
            _, df = Query().select(column).limit(1).get_scanner_data()
            print(f"✓ '{column}' works")
            working_columns.append(column)
        except Exception as e:
            print(f"❌ '{column}' fails: {e}")
            problematic_columns.append((column, str(e)))
            if 'ticker' in str(e).lower():
                print(f"🔍 '{column}' error mentions ticker!")

    print(f"\n=== Column Test Results ===")
    print(f"Working columns ({len(working_columns)}): {working_columns}")
    print(f"Problematic columns ({len(problematic_columns)}):")
    for col, error in problematic_columns:
        print(f"  {col}: {error}")


def debug_agent_prompt():
    """Check if the agent prompt mentions ticker"""

    print("\n=== Checking Agent Prompt for Ticker References ===\n")

    try:
        from agents.prompts import SCREENER_AGENT_PROMPT
        prompt_text = str(SCREENER_AGENT_PROMPT)

        if 'ticker' in prompt_text.lower():
            print("⚠️  Found 'ticker' in agent prompt!")
            lines = prompt_text.split('\n')
            for i, line in enumerate(lines):
                if 'ticker' in line.lower():
                    print(f"Line {i + 1}: {line.strip()}")
        else:
            print("✓ No 'ticker' found in agent prompt")

    except Exception as e:
        print(f"❌ Could not check prompt: {e}")


def test_working_manual_query():
    """Test the exact working manual query to confirm it still works"""

    print("\n=== Testing Known Working Manual Query ===\n")

    try:
        from tradingview_screener import Query, col

        print("Testing the manual query that worked...")

        _, df = (Query()
                 .select('name', 'close', 'volume', 'relative_volume_10d_calc', 'exchange')
                 .where(
            col('market_cap_basic').between(1_000_000, 50_000_000),
            col('relative_volume_10d_calc') > 1.2,
            col('exchange') != 'OTC'
        )
                 .order_by('volume', ascending=False)
                 .limit(10)
                 .get_scanner_data())

        print(f"✓ Manual query still works - {_} total results, {len(df)} returned")
        print(f"Sample results:")
        for _, row in df.head(3).iterrows():
            print(f"  {row['name']}: ${row['close']:.2f}")

    except Exception as e:
        print(f"❌ Manual query now fails: {e}")
        if 'ticker' in str(e).lower():
            print(f"🔍 Manual query error also mentions ticker - this is a broader issue!")


if __name__ == "__main__":
    debug_ticker_issue()
    debug_columns_step_by_step()
    debug_agent_prompt()
    test_working_manual_query()