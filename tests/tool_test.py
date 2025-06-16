
from dotenv import load_dotenv
from tools.tradingview_query import TradingViewQueryTool
from agents.screener_agent import ScreenerUpdateAgent
import json
load_dotenv()


def test_tool_only():
    """Test just the TradingView tool without any LLM tracking"""

    print("=== Testing TradingView Tool Only ===\n")

    # Import the tool directly


    # Create tool instance
    tool = TradingViewQueryTool()

    print("1. Testing basic tool functionality...")

    try:
        # Test basic query
        result = tool._run(
            columns=["name", "close", "change", "volume"],
            filters=[
                {"type": "greater_than", "column": "change", "value": 2.0},
                {"type": "greater_than", "column": "volume", "value": 100000}
            ],
            sort_column="change",
            sort_ascending=False,
            limit=10
        )

        print("✅ Tool executed successfully!")
        print(f"Result type: {type(result)}")
        print(f"Result length: {len(result) if isinstance(result, str) else 'N/A'}")
        print(f"Result preview: {result[:300]}...")

        # Try to parse the JSON result

        try:
            parsed = json.loads(result)
            print(f"\n📊 Parsed Results:")
            print(f"   Success: {parsed.get('success', 'N/A')}")
            print(f"   Total results: {parsed.get('total_results', 'N/A')}")
            print(f"   Returned results: {parsed.get('returned_results', 'N/A')}")

            if 'data_preview' in parsed and parsed['data_preview']:
                print(f"   Sample stocks:")
                for i, stock in enumerate(parsed['data_preview'][:5], 1):
                    name = stock.get('name', 'N/A')
                    change = stock.get('change', 'N/A')
                    volume = stock.get('volume', 'N/A')
                    print(f"     {i}. {name}: {change}% change, {volume:,} volume")

            return True

        except json.JSONDecodeError as e:
            print(f"❌ Could not parse JSON result: {e}")
            print(f"Raw result: {result}")
            return False

    except Exception as e:
        print(f"❌ Tool execution failed: {e}")
        return False


def test_agent_without_tracking():
    """Test agent without LLM usage tracking"""

    print("\n=== Testing Agent Without LLM Tracking ===\n")

    # Create agent without LLM tracking
    agent = ScreenerUpdateAgent(
        database_url="sqlite:///test_screener.db",
        model="gpt-4.1-nano"
    )

    # Simple prompt that should force tool usage
    test_prompt = """
    Execute a TradingView screener query immediately. Find stocks with:
    - change > 3%
    - volume > 100000

    Use columns: name, close, change, volume
    Sort by change descending, limit 5.

    Call tradingview_query tool now.
    """

    print("Sending simple test prompt to agent...")
    print("\n" + "=" * 50 + "\n")

    try:
        # Execute without LLM tracking
        result = agent.agent_executor.invoke({"input": test_prompt})

        print("Agent Response:")
        print(result.get('output', 'No output'))
        parsed = json.loads(result)
        print(f"\n📊 Parsed Results:")
        print(f"   Success: {parsed.get('success', 'N/A')}")
        print(f"   Total results: {parsed.get('total_results', 'N/A')}")
        print(f"   Returned results: {parsed.get('returned_results', 'N/A')}")

        if 'data_preview' in parsed and parsed['data_preview']:
            print(f"   Sample stocks:")
            for i, stock in enumerate(parsed['data_preview'][:5], 1):
                name = stock.get('name', 'N/A')
                change = stock.get('change', 'N/A')
                volume = stock.get('volume', 'N/A')
                print(f"     {i}. {name}: {change}% change, {volume:,} volume")

        return True

    except Exception as e:
        print(f"❌ Agent execution failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing TradingView functionality step by step...\n")

    # Test 1: Direct tool
    if test_tool_only():
        print("\n" + "=" * 60 + "\n")
        # Test 2: Agent without tracking
        test_agent_without_tracking()
    else:
        print("❌ Basic tool test failed - check TradingView setup")