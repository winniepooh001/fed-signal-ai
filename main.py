

# Initialize logging FIRST, before any other imports
from utils.logging_config import initialize_logging, ScreenerLogger

# Initialize the logging system
logger = initialize_logging(
    log_level="INFO",  # Change to DEBUG for more verbose logging
    console_output=True,
    log_dir="logs"
)
import os
from dotenv import load_dotenv
from workflow.email_workflow import EmailEnabledWorkflow

# Now import the separate agents
from agents.fed_analysis_agent import FedAnalysisAgent
from agents.screener_analysis_agent import ScreenerAnalysisAgent
from database import DatabaseManager

load_dotenv()

def get_smtp_config() -> dict:
    """Get SMTP configuration from environment variables"""
    return {
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', '587')),
        'sender_email': os.getenv('SENDER_EMAIL'),
        'sender_password': os.getenv('SENDER_PASSWORD'),
        'sender_name': os.getenv('SENDER_NAME', 'TradingView Screener Agent')
    }



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


def run_email_workflow():
    """Run the complete workflow with email integration"""

    logger.info("📧 RUNNING COMPLETE WORKFLOW WITH EMAIL")
    logger.info("=" * 80)

    # Check for email configuration
    smtp_config = get_smtp_config()

    if not smtp_config['sender_email'] or not smtp_config['sender_password']:
        logger.warning("⚠️ SMTP configuration incomplete - email functionality disabled")
        logger.warning("To enable email, set SENDER_EMAIL and SENDER_PASSWORD environment variables")

    # Get recipient emails from environment or use default
    recipient_emails_str = os.getenv('RECIPIENT_EMAILS', '')
    if recipient_emails_str:
        recipient_emails = [email.strip() for email in recipient_emails_str.split(',')]
    else:
        logger.warning("⚠️ No RECIPIENT_EMAILS set in environment - using demo email")
        recipient_emails = ["demo@example.com"]  # Replace with actual email for testing

    try:
        # Initialize email-enabled workflow
        workflow = EmailEnabledWorkflow(
            database_url="sqlite:///screener_data.db",
            model="gpt-4.1-mini",
            smtp_config=smtp_config
        )

        # Custom email message
        custom_message = (
            "This automated report contains stock screening results based on the latest "
            "Federal Reserve communications. The screening criteria have been optimized "
            "for the current market environment and policy stance."
        )

        # Run complete workflow
        result = workflow.run_complete_workflow_with_email(
            fed_url="https://www.federalreserve.gov/newsevents/pressreleases.htm",
            target_content="FOMC interest rates monetary policy",
            recipient_emails=recipient_emails,
            custom_email_message=custom_message
        )

        return result['workflow_success']

    except Exception as e:
        logger.error(f"Email workflow failed: {e}", exc_info=True)
        return False

def main():
    """Refactored main function with clear two-agent workflow"""

    logger.info("Initializing Two-Agent Screener System")

    try:
        # Initialize separate agents
        run_email_workflow()

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