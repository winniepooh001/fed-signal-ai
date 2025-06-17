# workflows/email_workflow.py
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from agents.fed_analysis_agent import FedAnalysisAgent
from agents.screener_analysis_agent import ScreenerAnalysisAgent
from agents.email_agent import EmailAgent, send_screener_email
from database import DatabaseManager
from utils.logging_config import get_logger

logger = get_logger()


class EmailEnabledWorkflow:
    """Enhanced workflow that includes email capabilities"""

    def __init__(self,
                 database_url: str,
                 model: str = "gpt-4o-mini",
                 smtp_config: Optional[Dict] = None):
        """
        Initialize the email-enabled workflow

        Args:
            database_url: Database connection string
            model: LLM model to use
            smtp_config: SMTP configuration for email sending
        """

        logger.info("Initializing Email-Enabled Workflow")

        # Initialize database manager
        self.db_manager = DatabaseManager(database_url)
        self.db_manager.create_tables()

        # Initialize agents
        self.fed_agent = FedAnalysisAgent(
            database_url=database_url,
            model=model,
            temperature=0
        )

        self.screener_agent = ScreenerAnalysisAgent(
            database_url=database_url,
            model=model,
            temperature=0
        )

        # Initialize email agent
        self.email_agent = EmailAgent(
            db_manager=self.db_manager,
            smtp_config=smtp_config
        )

        logger.info("Email-enabled workflow initialized successfully")

    def run_complete_workflow_with_email(self,
                                         fed_url: str,
                                         target_content: str,
                                         recipient_emails: List[str],
                                         custom_email_message: Optional[str] = None) -> Dict[str, Any]:
        """
        Run complete workflow: Fed analysis → Screener → Email results

        Args:
            fed_url: Fed website URL to analyze
            target_content: Content to look for in Fed data
            recipient_emails: List of email addresses to send results to
            custom_email_message: Optional custom message for email

        Returns:
            Dict with complete workflow results
        """

        logger.info("=" * 80)
        logger.info("STARTING COMPLETE WORKFLOW WITH EMAIL")
        logger.info("=" * 80)

        workflow_results = {
            'fed_analysis': None,
            'screener_results': None,
            'email_results': None,
            'workflow_success': False,
            'total_llm_cost': 0.0,
            'screener_result_ids': []
        }

        try:
            # Step 1: Fed Analysis
            logger.info("STEP 1: Federal Reserve Data Analysis")
            logger.info("-" * 50)

            fed_result = self.fed_agent.analyze_fed_data(
                fed_url=fed_url,
                target_content=target_content
            )

            workflow_results['fed_analysis'] = fed_result
            workflow_results['total_llm_cost'] += fed_result.get('llm_usage', {}).get('total_cost', 0.0)

            if not fed_result['success']:
                logger.error(f"Fed analysis failed: {fed_result.get('error')}")
                return workflow_results

            logger.info(f"✅ Fed analysis completed successfully")
            logger.info(f"Market environment: {fed_result['analysis_result'].get('market_environment', 'N/A')}")
            logger.info(f"Policy stance: {fed_result['analysis_result'].get('policy_stance', 'N/A')}")

            # Step 2: Conditional Screener Creation
            if fed_result['screening_needed']:
                logger.info("STEP 2: Creating Stock Screener")
                logger.info("-" * 50)

                screener_result = self.screener_agent.create_screener_from_analysis(
                    fed_analysis=fed_result
                )

                workflow_results['screener_results'] = screener_result
                workflow_results['total_llm_cost'] += screener_result.get('llm_usage', {}).get('total_cost', 0.0)

                if not screener_result['success']:
                    logger.error(f"Screener creation failed: {screener_result.get('error')}")
                    return workflow_results

                logger.info(f"✅ Screener completed successfully")

                # Extract screener result ID for email
                screener_data = screener_result.get('screener_results', {})
                tradingview_data = screener_data.get('tradingview_data', {})
                screener_result_id = tradingview_data.get('screener_result_id')

                if screener_result_id:
                    workflow_results['screener_result_ids'].append(screener_result_id)

                    logger.info(f"Total stocks found: {screener_data.get('total_results', 0)}")
                    logger.info(f"Stocks returned: {screener_data.get('returned_results', 0)}")

                    # Step 3: Email Results
                    if recipient_emails:
                        logger.info("STEP 3: Sending Email Report")
                        logger.info("-" * 50)

                        email_result = send_screener_email(
                            db_manager=self.db_manager,
                            screener_result_id=screener_result_id,
                            recipient_emails=recipient_emails,
                            custom_message=custom_email_message
                        )

                        workflow_results['email_results'] = email_result

                        if email_result['success']:
                            logger.info(f"✅ Email sent successfully to {len(recipient_emails)} recipients")
                            workflow_results['workflow_success'] = True
                        else:
                            logger.error(f"❌ Email sending failed: {email_result.get('error')}")
                            # Still consider workflow successful if screening worked
                            workflow_results['workflow_success'] = True
                    else:
                        logger.info("📧 No email recipients provided - skipping email step")
                        workflow_results['workflow_success'] = True
                else:
                    logger.warning("⚠️ No screener result ID found - cannot send email")
                    workflow_results['workflow_success'] = True
            else:
                logger.info("🔄 Screening not needed based on Fed analysis")
                workflow_results['workflow_success'] = True

        except Exception as e:
            logger.error(f"Workflow failed with error: {str(e)}", exc_info=True)
            workflow_results['error'] = str(e)

        # Final Summary
        logger.info("=" * 80)
        logger.info("WORKFLOW SUMMARY")
        logger.info("=" * 80)
        logger.info(
            f"Fed Analysis: {'✅ SUCCESS' if workflow_results['fed_analysis'] and workflow_results['fed_analysis']['success'] else '❌ FAILED'}")
        logger.info(
            f"Screener: {'✅ SUCCESS' if workflow_results['screener_results'] and workflow_results['screener_results']['success'] else '🔄 SKIPPED'}")
        logger.info(
            f"Email: {'✅ SUCCESS' if workflow_results['email_results'] and workflow_results['email_results']['success'] else '📧 SKIPPED'}")
        logger.info(f"Total LLM Cost: ${workflow_results['total_llm_cost']:.4f}")
        logger.info(f"Overall Success: {'✅ YES' if workflow_results['workflow_success'] else '❌ NO'}")
        logger.info("=" * 80)

        return workflow_results

    def send_historical_screener_results(self,
                                         execution_id: str,
                                         recipient_emails: List[str],
                                         custom_message: Optional[str] = None) -> Dict[str, Any]:
        """
        Send email for historical screener results by execution ID

        Args:
            execution_id: Agent execution ID to find screener results for
            recipient_emails: Email addresses to send to
            custom_message: Optional custom message

        Returns:
            Dict with email sending results
        """

        logger.info(f"Sending historical screener results for execution: {execution_id}")

        try:
            # Get screener results for this execution
            screener_results = self.screener_agent.get_screener_results_by_execution(execution_id)

            if not screener_results:
                return {
                    'success': False,
                    'error': f'No screener results found for execution {execution_id}'
                }

            # Send email for the most recent result
            latest_result = screener_results[0]  # Assuming sorted by recency
            screener_result_id = latest_result['result_id']

            email_result = send_screener_email(
                db_manager=self.db_manager,
                screener_result_id=screener_result_id,
                recipient_emails=recipient_emails,
                custom_message=custom_message
            )

            logger.info(f"Historical screener email result: {email_result['success']}")
            return email_result

        except Exception as e:
            logger.error(f"Error sending historical screener results: {e}")
            return {
                'success': False,
                'error': str(e),
                'execution_id': execution_id
            }

    def get_recent_results_summary(self, limit: int = 5) -> Dict[str, Any]:
        """
        Get summary of recent results for email workflow tracking

        Args:
            limit: Number of recent results to retrieve

        Returns:
            Dict with recent results summary
        """

        try:
            fed_history = self.fed_agent.get_analysis_history(limit=limit)
            screener_history = self.screener_agent.get_screener_history(limit=limit)

            return {
                'success': True,
                'fed_analyses': fed_history,
                'screener_executions': screener_history,
                'summary': {
                    'total_fed_analyses': len(fed_history),
                    'total_screener_executions': len(screener_history),
                    'recent_activity': datetime.now().isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Error getting recent results summary: {e}")
            return {
                'success': False,
                'error': str(e)
            }