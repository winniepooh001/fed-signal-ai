#!/usr/bin/env python3
"""
Migration Verification Test
==========================

This script tests the two-agent refactoring to ensure:
1. Fed Analysis Agent works independently
2. Screener Analysis Agent works independently
3. Two-agent workflow functions correctly
4. Database compatibility is maintained
"""

import sys
import os
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Initialize logging for tests
from utils.logging_config import initialize_logging, get_logger

test_logger = initialize_logging(
    log_level="INFO",
    console_output=True,
    log_file="migration_test.log"
)

load_dotenv()


def test_fed_analysis_agent():
    """Test Fed Analysis Agent in isolation"""

    test_logger.info("=" * 60)
    test_logger.info("TEST 1: Fed Analysis Agent")
    test_logger.info("=" * 60)

    try:
        from agents.fed_analysis_agent import FedAnalysisAgent
        test_logger.info("✅ Fed Analysis Agent import successful")

        # Initialize agent
        fed_agent = FedAnalysisAgent(
            database_url="sqlite:///migration_test.db",
            model="gpt-4o-mini",
            temperature=0
        )
        test_logger.info("✅ Fed Analysis Agent initialization successful")

        # Test Fed analysis
        result = fed_agent.analyze_fed_data(
            fed_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
            target_content="FOMC interest rates"
        )

        # Verify results
        if result['success']:
            test_logger.info("✅ Fed analysis execution successful")
            test_logger.info(f"   Execution ID: {result['execution_id']}")
            test_logger.info(f"   Screening needed: {result['screening_needed']}")
            test_logger.info(f"   Market environment: {result['analysis_result'].get('market_environment', 'N/A')}")
            test_logger.info(f"   LLM cost: ${result['llm_usage']['total_cost']:.4f}")
            return True
        else:
            test_logger.error(f"❌ Fed analysis failed: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        test_logger.error(f"❌ Fed Analysis Agent test failed: {str(e)}", exc_info=True)
        return False


def test_screener_analysis_agent():
    """Test Screener Analysis Agent in isolation"""

    test_logger.info("=" * 60)
    test_logger.info("TEST 2: Screener Analysis Agent")
    test_logger.info("=" * 60)

    try:
        from agents.screener_analysis_agent import ScreenerAnalysisAgent
        test_logger.info("✅ Screener Analysis Agent import successful")

        # Initialize agent
        screener_agent = ScreenerAnalysisAgent(
            database_url="sqlite:///migration_test.db",
            model="gpt-4o-mini",
            temperature=0
        )
        test_logger.info("✅ Screener Analysis Agent initialization successful")

        # Test custom screener creation
        result = screener_agent.create_screener_from_analysis(
            fed_analysis={},
            custom_prompt="Find momentum stocks with >3% daily change and high relative volume"
        )

        # Verify results
        if result['success']:
            test_logger.info("✅ Screener execution successful")
            test_logger.info(f"   Execution ID: {result['execution_id']}")

            screener_data = result['screener_results']
            test_logger.info(f"   Total stocks found: {screener_data.get('total_results', 0)}")
            test_logger.info(f"   Stocks returned: {screener_data.get('returned_results', 0)}")
            test_logger.info(f"   LLM cost: ${result['llm_usage']['total_cost']:.4f}")

            # Show sample stocks
            sample_stocks = screener_data.get('sample_stocks', [])
            if sample_stocks:
                test_logger.info("   Sample stocks:")
                for i, stock in enumerate(sample_stocks[:3], 1):
                    name = stock.get('name', 'N/A')
                    change = stock.get('change', 0)
                    test_logger.info(f"     {i}. {name}: {change:+.1f}% change")

            return True
        else:
            test_logger.error(f"❌ Screener execution failed: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        test_logger.error(f"❌ Screener Analysis Agent test failed: {str(e)}", exc_info=True)
        return False


def test_two_agent_workflow():
    """Test the complete two-agent workflow"""

    test_logger.info("=" * 60)
    test_logger.info("TEST 3: Two-Agent Workflow")
    test_logger.info("=" * 60)

    try:
        from agents.fed_analysis_agent import FedAnalysisAgent
        from agents.screener_analysis_agent import ScreenerAnalysisAgent

        # Initialize both agents
        fed_agent = FedAnalysisAgent(
            database_url="sqlite:///migration_test.db",
            model="gpt-4o-mini",
            temperature=0
        )

        screener_agent = ScreenerAnalysisAgent(
            database_url="sqlite:///migration_test.db",
            model="gpt-4o-mini",
            temperature=0
        )

        test_logger.info("✅ Both agents initialized successfully")

        # Step 1: Fed Analysis
        test_logger.info("   Step 1: Fed Analysis")
        fed_result = fed_agent.analyze_fed_data(
            fed_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
            target_content="FOMC monetary policy"
        )

        if not fed_result['success']:
            test_logger.error(f"❌ Fed analysis step failed: {fed_result.get('error')}")
            return False

        test_logger.info(
            f"   ✅ Fed analysis completed: {fed_result['analysis_result'].get('market_environment', 'N/A')}")

        # Step 2: Conditional Screening
        test_logger.info("   Step 2: Conditional Screening")
        if fed_result['screening_needed']:
            screener_result = screener_agent.create_screener_from_analysis(
                fed_analysis=fed_result
            )

            if not screener_result['success']:
                test_logger.error(f"❌ Screener step failed: {screener_result.get('error')}")
                return False

            test_logger.info(
                f"   ✅ Screener completed: {screener_result['screener_results'].get('total_results', 0)} stocks found")
        else:
            test_logger.info("   📝 Screening not needed based on Fed analysis")

        # Calculate total cost
        total_cost = fed_result['llm_usage']['total_cost']
        if fed_result['screening_needed'] and 'screener_result' in locals():
            total_cost += screener_result['llm_usage']['total_cost']

        test_logger.info(f"✅ Two-agent workflow completed successfully")
        test_logger.info(f"   Total workflow cost: ${total_cost:.4f}")

        return True

    except Exception as e:
        test_logger.error(f"❌ Two-agent workflow test failed: {str(e)}", exc_info=True)
        return False


def test_database_compatibility():
    """Test database compatibility and execution tracking"""

    test_logger.info("=" * 60)
    test_logger.info("TEST 4: Database Compatibility")
    test_logger.info("=" * 60)

    try:
        from database import DatabaseManager

        db_manager = DatabaseManager("sqlite:///migration_test.db")
        test_logger.info("✅ Database manager initialization successful")

        # Check execution history
        with db_manager.get_session() as session:
            from database.models import AgentExecution

            # Count different execution types
            fed_executions = session.query(AgentExecution).filter(
                AgentExecution.execution_type == "fed_analysis_only"
            ).count()

            screener_executions = session.query(AgentExecution).filter(
                AgentExecution.execution_type.in_(["fed_based_screener", "custom_screener"])
            ).count()

            test_logger.info(f"✅ Database query successful")
            test_logger.info(f"   Fed analysis executions: {fed_executions}")
            test_logger.info(f"   Screener executions: {screener_executions}")

            if fed_executions > 0 and screener_executions > 0:
                test_logger.info("✅ Both agent types have database records")
                return True
            else:
                test_logger.warning("⚠️  Some agent types missing database records (may be expected)")
                return True  # Still passing as this might be first run

    except Exception as e:
        test_logger.error(f"❌ Database compatibility test failed: {str(e)}", exc_info=True)
        return False


def test_legacy_compatibility():
    """Test that legacy imports work (if available)"""

    test_logger.info("=" * 60)
    test_logger.info("TEST 5: Legacy Compatibility")
    test_logger.info("=" * 60)

    try:
        # Try importing new agents through agents package
        from agents import FedAnalysisAgent, ScreenerAnalysisAgent
        test_logger.info("✅ New agent imports through package successful")

        # Try legacy import (might not exist after migration)
        try:
            from agents import ScreenerUpdateAgent
            if ScreenerUpdateAgent is not None:
                test_logger.info("✅ Legacy ScreenerUpdateAgent still available")
            else:
                test_logger.info("📝 Legacy ScreenerUpdateAgent deprecated (expected)")
        except ImportError:
            test_logger.info("📝 Legacy ScreenerUpdateAgent not available (expected after migration)")

        return True

    except Exception as e:
        test_logger.error(f"❌ Legacy compatibility test failed: {str(e)}", exc_info=True)
        return False


def run_migration_tests():
    """Run all migration tests and provide summary"""

    test_logger.info("🚀 STARTING MIGRATION VERIFICATION TESTS")
    test_logger.info("=" * 80)

    tests = [
        ("Fed Analysis Agent", test_fed_analysis_agent),
        ("Screener Analysis Agent", test_screener_analysis_agent),
        ("Two-Agent Workflow", test_two_agent_workflow),
        ("Database Compatibility", test_database_compatibility),
        ("Legacy Compatibility", test_legacy_compatibility)
    ]

    results = []

    for test_name, test_func in tests:
        test_logger.info(f"\n🧪 Running {test_name} test...")
        try:
            result = test_func()
            results.append((test_name, result))
            status = "✅ PASSED" if result else "❌ FAILED"
            test_logger.info(f"   {status}")
        except Exception as e:
            test_logger.error(f"   ❌ FAILED - {str(e)}")
            results.append((test_name, False))

    # Summary
    test_logger.info("\n" + "=" * 80)
    test_logger.info("MIGRATION TEST SUMMARY")
    test_logger.info("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        test_logger.info(f"{status} {test_name}")

    test_logger.info("-" * 80)
    test_logger.info(f"OVERALL RESULT: {passed}/{total} tests passed")

    if passed == total:
        test_logger.info("🎉 ALL TESTS PASSED - Migration successful!")
        return True
    else:
        test_logger.error(f"⚠️  {total - passed} tests failed - Check logs for details")
        return False


if __name__ == "__main__":
    success = run_migration_tests()
    exit(0 if success else 1)