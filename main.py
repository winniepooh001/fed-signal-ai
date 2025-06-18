

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
from workflow.enhanced_workflow import EnhancedMainAgent

# Now import the separate agents
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




def main():
    """Main function with corrected workflow"""

    logger.info("Starting Enhanced Main Agent with Corrected Logic")

    try:
        # Initialize enhanced agent
        agent = EnhancedMainAgent()

        # Run workflow
        result = agent.run_workflow(output_dir="output")

        if result['workflow_success']:
            logger.info("✅ WORKFLOW COMPLETED SUCCESSFULLY")
        else:
            logger.info("❌ WORKFLOW COMPLETED WITH ISSUES")

    except Exception as e:
        logger.critical(f"System failed: {str(e)}", exc_info=True)
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