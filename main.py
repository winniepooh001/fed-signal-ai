import os
from agents.screener_agent import ScreenerUpdateAgent
from database import DatabaseManager
from dotenv import load_dotenv
load_dotenv()

def main():
    """Example usage with database persistence"""

    # Initialize agent with local SQLite database
    agent = ScreenerUpdateAgent(
        temperature=0,
        database_url="sqlite:///screener_data.db",  # Local SQLite file
        model="gpt-4.1-mini"
    )

    print("=== Screener Update Agent with Database Persistence ===\n")

    # Example 1: Fed analysis with full persistence
    print("1. Analyzing Fed data...")
    fed_result = agent.analyze_fed_data_and_update_screeners(
        fed_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
        target_content="FOMC interest rates monetary policy"
    )

    if fed_result['success']:
        print(f"✅ Fed analysis completed. Execution ID: {fed_result['execution_id']}")

        # Display LLM usage
        llm_usage = fed_result['llm_usage']
        print(f"\n📊 LLM Usage for this execution:")
        print(f"   Total calls: {llm_usage['total_calls']}")
        print(f"   Total tokens: {llm_usage['total_tokens']}")
        print(f"   Prompt tokens: {llm_usage['total_prompt_tokens']}")
        print(f"   Completion tokens: {llm_usage['total_completion_tokens']}")
        print(f"   Estimated cost: ${llm_usage['total_cost']:.4f}")

        if llm_usage['breakdown']:
            print(f"\n   Breakdown by model:")
            for model, stats in llm_usage['breakdown'].items():
                print(f"     {model}: {stats['calls']} calls, {stats['total_tokens']} tokens, ${stats['cost']:.4f}")

    else:
        print(f"❌ Fed analysis failed: {fed_result['error']}")
        if 'llm_usage' in fed_result:
            print(f"💰 LLM cost incurred: ${fed_result['llm_usage']['total_cost']:.4f}")

        # Get overall usage statistics
    print(f"\n📈 Overall usage statistics (last 24 hours):")
    overall_stats = agent.get_usage_statistics(time_range_hours=24)
    print(f"   Total LLM calls: {overall_stats['total_calls']}")
    print(f"   Total tokens used: {overall_stats['total_tokens']}")
    print(f"   Total estimated cost: ${overall_stats['total_cost']:.4f}")

    print("\n" + "=" * 50 + "\n")

    # Example 2: Custom analysis
    print("2. Creating custom screeners...")
    custom_result = agent.create_custom_screeners(
        "Based on current market conditions, execute the most promising stock screener. "
        "Consider reaction in the stock market in the next 1 - 4 from the press release"
        "Execute one screening strategies that make sense right now."
    )

    if custom_result['success']:
        print(f"✅ Custom analysis completed. Execution ID: {custom_result['execution_id']}")
    else:
        print(f"❌ Custom analysis failed: {custom_result['error']}")

    print("\n" + "=" * 50 + "\n")

    # Example 3: View execution history
    print("3. Recent execution history:")
    history = agent.get_execution_history(limit=5)
    for exec in history:
        status = "✅" if exec['success'] else "❌"
        print(f"{status} {exec['execution_type']}: {exec['user_prompt'][:100]}...")
        print(f"   Started: {exec['started_at']}")

    print("\n=== Database Integration Complete ===")


def setup_database():
    """Helper function to set up local SQLite database"""
    print("Setting up local SQLite database...")


    db_manager = DatabaseManager("sqlite:///screener_data.db")
    db_manager.create_tables()

    print("Local database setup complete! (screener_data.db created)")


if __name__=="__main__":
    main()
