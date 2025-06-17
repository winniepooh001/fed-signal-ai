import os
from dotenv import load_dotenv

# Initialize logging FIRST, before any other imports
from utils.logging_config import initialize_logging, ScreenerLogger

# Initialize the logging system
logger = initialize_logging(
    log_level="INFO",  # Change to DEBUG for more verbose logging
    console_output=True,
    log_dir="logs"
)

# Now import the separate agents
from agents.fed_analysis_agent import FedAnalysisAgent
from agents.screener_analysis_agent import ScreenerAnalysisAgent
from database import DatabaseManager

load_dotenv()


def run_fed_analysis_workflow(fed_agent: FedAnalysisAgent,
                              screener_agent: ScreenerAnalysisAgent,
                              fed_url: str,
                              target_content: str) -> dict:
    """
    Run the two-step Fed analysis workflow:
    1. Analyze Fed data and decide if screening is needed
    2. If needed, create and execute screener based on analysis
    """

    logger.info("=" * 60)
    logger.info("STARTING FED ANALYSIS WORKFLOW")
    logger.info("=" * 60)

    workflow_results = {
        'fed_analysis': None,
        'screener_results': None,
        'workflow_success': False,
        'total_llm_cost': 0.0
    }

    # Step 1: Fed Analysis Only
    logger.info("STEP 1: Fed Data Analysis")
    logger.info("-" * 30)

    fed_result = fed_agent.analyze_fed_data(
        fed_url=fed_url,
        target_content=target_content
    )

    workflow_results['fed_analysis'] = fed_result
    workflow_results['total_llm_cost'] += fed_result.get('llm_usage', {}).get('total_cost', 0.0)

    if fed_result['success']:
        logger.info(f"✅ Fed analysis completed successfully")
        logger.info(f"Execution ID: {fed_result['execution_id']}")
        logger.info(f"Analysis result: {fed_result['analysis_result']}")
        logger.info(f"Screening needed: {fed_result['screening_needed']}")

        # Step 2: Conditional Screener Creation
        if fed_result['screening_needed']:
            logger.info("STEP 2: Creating Screener Based on Fed Analysis")
            logger.info("-" * 30)

            screener_result = screener_agent.create_screener_from_analysis(
                fed_analysis=fed_result
            )

            workflow_results['screener_results'] = screener_result
            workflow_results['total_llm_cost'] += screener_result.get('llm_usage', {}).get('total_cost', 0.0)

            if screener_result['success']:
                logger.info(f"✅ Screener created successfully")
                logger.info(f"Execution ID: {screener_result['execution_id']}")

                # Log screener results summary
                screener_data = screener_result.get('screener_results', {})
                logger.info(f"Total stocks found: {screener_data.get('total_results', 0)}")
                logger.info(f"Stocks returned: {screener_data.get('returned_results', 0)}")

                if screener_data.get('sample_stocks'):
                    logger.info("Sample stocks:")
                    for i, stock in enumerate(screener_data['sample_stocks'][:5], 1):
                        name = stock.get('name', 'N/A')
                        change = stock.get('change', 0)
                        volume = stock.get('volume', 0)
                        logger.info(f"  {i}. {name}: {change:+.1f}% change, {volume:,} volume")

                workflow_results['workflow_success'] = True

            else:
                logger.error(f"❌ Screener creation failed: {screener_result.get('error', 'Unknown error')}")
        else:
            logger.info("🔄 Screening not needed based on Fed analysis")
            workflow_results['workflow_success'] = True  # Workflow succeeded, just no screening needed

    else:
        logger.error(f"❌ Fed analysis failed: {fed_result.get('error', 'Unknown error')}")

    # Workflow Summary
    logger.info("=" * 60)
    logger.info("FED ANALYSIS WORKFLOW SUMMARY")
    logger.info(f"Total LLM Cost: ${workflow_results['total_llm_cost']:.4f}")
    logger.info(f"Workflow Success: {workflow_results['workflow_success']}")
    logger.info("=" * 60)

    return workflow_results


def main():
    """Refactored main function with clear two-agent workflow"""

    logger.info("Initializing Two-Agent Screener System")

    try:
        # Initialize separate agents
        logger.info("Setting up Fed Analysis Agent...")
        fed_agent = FedAnalysisAgent(
            database_url="sqlite:///screener_data.db",
            model="gpt-4o-mini",
            temperature=0
        )

        logger.info("Setting up Screener Analysis Agent...")
        screener_agent = ScreenerAnalysisAgent(
            database_url="sqlite:///screener_data.db",
            model="gpt-4o-mini",
            temperature=0
        )

        logger.info("Both agents initialized successfully")

        # Workflow 1: Fed Analysis → Conditional Screening
        logger.info("Starting Fed analysis workflow...")
        fed_workflow_result = run_fed_analysis_workflow(
            fed_agent=fed_agent,
            screener_agent=screener_agent,
            fed_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
            target_content="FOMC interest rates monetary policy"
        )
        fed_success = fed_workflow_result.get('workflow_success', False)
        fed_cost = fed_workflow_result.get('total_llm_cost', 0.0)
        logger.info(f"Fed Workflow: {'✅ SUCCESS' if fed_success else '❌ FAILED'} - Cost: ${fed_cost:.4f}")

        # Execution history
        logger.info("Recent execution history:")
        fed_history = fed_agent.get_analysis_history(limit=3)
        screener_history = screener_agent.get_screener_history(limit=3)

        logger.info("Fed Analysis History:")
        for exec in fed_history:
            status = "✅" if exec['success'] else "❌"
            logger.info(f"  {status} {exec['started_at']}: {exec['user_prompt'][:100]}...")

        logger.info("Screener Execution History:")
        for exec in screener_history:
            status = "✅" if exec['success'] else "❌"
            logger.info(f"  {status} {exec['execution_type']}: {exec['user_prompt'][:100]}...")


    except Exception as e:
        logger.critical(f"System failed with critical error: {str(e)}", exc_info=True)
        raise


def setup_database():

    logger.info("Setting up local SQLite database...")

    try:
        db_manager = DatabaseManager("sqlite:///screener_data.db")
        db_manager.create_tables()

        logger.info("Local database setup completed successfully (screener_data.db created)")

    except Exception as e:
        logger.error(f"Database setup failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        # Log system information
        ScreenerLogger.log_system_info()

        main()

        logger.info("SCREENER SYSTEM COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.warning("System interrupted by user (Ctrl+C)")
    except Exception as e:
        logger.critical(f"System failed with critical error: {str(e)}", exc_info=True)
        exit(1)