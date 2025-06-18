import sys

sys.path.append("..")

import json

from tools.tradingview_query import TradingViewQueryTool


def test_tool_filtering():
    """Test if our tool applies mandatory filters correctly"""

    print("=== Testing Tool Filter Application ===\n")

    # Create tool instance
    tool = TradingViewQueryTool()

    # Test 1: Basic momentum query (should get mandatory filters)
    print("1. Testing momentum query with tool mandatory filters:")
    try:
        result_json = tool._run(
            columns=["name", "close", "change", "volume", "market_cap_basic"],
            filters=[{"type": "greater_than", "column": "change", "value": 3.0}],
            sort_column="change",
            limit=10,
        )

        result = json.loads(result_json)
        print(f"   Total results: {result['total_results']}")
        print(f"   Returned results: {result['returned_results']}")
        print(f"   Success: {result['success']}")

        # Check data quality
        if result["data_preview"]:
            print("   Sample results:")
            for i, stock in enumerate(result["data_preview"][:5], 1):
                name = stock.get("name", "N/A")
                close = stock.get("close", 0)
                change = stock.get("change", 0)
                volume = stock.get("volume", 0)
                market_cap = stock.get("market_cap_basic", 0)

                print(
                    f"     {i}. {name}: ${close:.2f}, {change:+.1f}%, {volume:,.0f} vol, ${market_cap:,.0f} mcap"
                )

                # Quality checks
                issues = []
                if close < 10:
                    issues.append("LOW_PRICE")
                if volume < 1000000:
                    issues.append("LOW_VOLUME")
                if market_cap < 5000000000:
                    issues.append("LOW_MCAP")
                if change > 1000:
                    issues.append("EXTREME_CHANGE")

                if issues:
                    print(f"        ⚠️  QUALITY ISSUES: {', '.join(issues)}")
                else:
                    print("        ✅ Quality OK")

        print()

    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Test 2: High performance query (should exclude extreme values)
    print("2. Testing high performance query:")
    try:
        result_json = tool._run(
            columns=["name", "close", "Perf.Y", "volume", "market_cap_basic"],
            filters=[{"type": "greater_than", "column": "Perf.Y", "value": 20}],
            sort_column="Perf.Y",
            limit=10,
        )

        result = json.loads(result_json)
        print(f"   Total results: {result['total_results']}")
        print(f"   Returned results: {result['returned_results']}")

        if result["data_preview"]:
            print("   Performance range check:")
            perfs = [
                stock.get("Perf.Y", 0)
                for stock in result["data_preview"]
                if stock.get("Perf.Y")
            ]
            if perfs:
                print(f"     Min performance: {min(perfs):.1f}%")
                print(f"     Max performance: {max(perfs):.1f}%")

                # Check for extreme values
                extreme_count = sum(1 for p in perfs if p > 1000)
                if extreme_count > 0:
                    print(
                        f"     ⚠️  {extreme_count} stocks with >1000% performance (likely data errors)"
                    )
                else:
                    print("     ✅ No extreme performance values detected")

        print()

    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Test 3: Compare with manual query (same filters)
    print("3. Comparing tool vs manual query:")
    try:
        from tradingview_screener import Query, col

        # Manual query with same filters
        _, df_manual = (
            Query()
            .select("name", "close", "change", "volume", "market_cap_basic")
            .where(
                col("exchange") != "OTC",
                col("market_cap_basic") > 5000000000,
                col("volume") > 1000000,
                col("close") > 10,
                col("close") < 1000,
                col("relative_volume_10d_calc") > 0.3,
                col("change") > 3.0,
            )
            .order_by("change", ascending=False)
            .limit(10)
            .get_scanner_data()
        )

        # Tool query
        result_json = tool._run(
            columns=["name", "close", "change", "volume", "market_cap_basic"],
            filters=[{"type": "greater_than", "column": "change", "value": 3.0}],
            sort_column="change",
            limit=10,
        )
        result_tool = json.loads(result_json)

        print(f"   Manual query total results: {_}")
        print(f"   Tool query total results: {result_tool['total_results']}")
        print(f"   Difference: {abs(_ - result_tool['total_results'])}")

        if abs(_ - result_tool["total_results"]) < 50:  # Allow small differences
            print("   ✅ Results are similar - filters working correctly")
        else:
            print("   ⚠️  Large difference - tool filters may not be working")

        # Compare top results
        if not df_manual.empty and result_tool["data_preview"]:
            print("\n   Top stock comparison:")
            manual_top = df_manual.iloc[0]
            tool_top = result_tool["data_preview"][0]

            print(f"     Manual: {manual_top['name']} ({manual_top['change']:+.1f}%)")
            print(
                f"     Tool:   {tool_top.get('name', 'N/A')} ({tool_top.get('change', 0):+.1f}%)"
            )

        print()

    except Exception as e:
        print(f"   ❌ Error in comparison: {e}\n")


def test_filter_edge_cases():
    """Test edge cases and filter effectiveness"""

    print("=== Testing Filter Edge Cases ===\n")

    tool = TradingViewQueryTool()

    # Test 1: Query that should return very few results
    print("1. Testing restrictive query (should return <100 results):")
    try:
        result_json = tool._run(
            columns=["name", "close", "change", "volume", "market_cap_basic"],
            filters=[
                {"type": "greater_than", "column": "change", "value": 5.0},
                {"type": "greater_than", "column": "volume", "value": 5000000},
                {
                    "type": "greater_than",
                    "column": "market_cap_basic",
                    "value": 20000000000,
                },
            ],
            sort_column="change",
            limit=50,
        )

        result = json.loads(result_json)
        print(f"   Total results: {result['total_results']}")

        if result["total_results"] < 100:
            print("   ✅ Good - restrictive filters working")
        else:
            print("   ⚠️  Too many results - filters may not be restrictive enough")

        print()

    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Test 2: Query with no additional filters (just mandatory)
    print("2. Testing mandatory filters only:")
    try:
        result_json = tool._run(
            columns=["name", "close", "volume", "market_cap_basic"],
            filters=[],  # No user filters
            sort_column="volume",
            limit=10,
        )

        result = json.loads(result_json)
        print(
            f"   Total results with mandatory filters only: {result['total_results']}"
        )

        # Should be significantly less than 18,507 (baseline)
        if result["total_results"] < 5000:
            print("   ✅ Mandatory filters are working (reduced from ~18,507)")
        else:
            print("   ❌ Mandatory filters not working effectively")

        # Check data quality
        if result["data_preview"]:
            all_quality_ok = True
            for stock in result["data_preview"]:
                close = stock.get("close", 0)
                volume = stock.get("volume", 0)
                market_cap = stock.get("market_cap_basic", 0)

                if close < 10 or volume < 1000000 or market_cap < 5000000000:
                    all_quality_ok = False
                    break

            if all_quality_ok:
                print("   ✅ All returned stocks meet quality criteria")
            else:
                print("   ❌ Some stocks don't meet mandatory filter criteria")

        print()

    except Exception as e:
        print(f"   ❌ Error: {e}\n")


if __name__ == "__main__":
    test_tool_filtering()
    test_filter_edge_cases()
