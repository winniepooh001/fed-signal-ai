

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