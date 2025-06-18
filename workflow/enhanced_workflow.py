from database.database import DatabaseManager
from agents.market_movement_analyzer import MarketMovementAnalyzer
from agents.screener_analysis_agent import ScreenerAnalysisAgent
from typing import Dict, Any, List
from utils.logging_config import get_logger
from market_data.data_fetch import DatabaseIntegratedMarketDataFetcher
from agents.email_agent import send_screener_email
import os
import glob
import json

from datetime import datetime

logger = get_logger(__name__)


class EnhancedMainAgent:
    """Main agent with corrected market integration logic"""

    def __init__(self, database_url: str = "sqlite:///screener_data.db", model: str = "gpt-4o-mini"):
        self.database_url = database_url
        self.db_manager = DatabaseManager(database_url)
        self.db_manager.create_tables()

        # Initialize market fetcher for current snapshot
        self.market_fetcher = DatabaseIntegratedMarketDataFetcher(database_url)

        # Initialize market movement analyzer
        self.movement_analyzer = MarketMovementAnalyzer(model=model)

        # Initialize screener agent
        self.screener_agent = ScreenerAnalysisAgent(
            database_url=database_url,
            model=model,
            temperature=0
        )

        logger.info("Enhanced Main Agent initialized")

    def run_workflow(self, output_dir: str = "output") -> Dict[str, Any]:
        """
        Run the corrected workflow

        Args:
            output_dir: Directory to check for JSON files

        Returns:
            Dict with workflow results
        """

        logger.info("=" * 80)
        logger.info("STARTING ENHANCED MAIN AGENT WORKFLOW")
        logger.info("=" * 80)

        workflow_results = {
            'json_files_found': [],
            'historical_market_data': None,
            'current_market_data': None,
            'market_movement_analysis': None,
            'fed_content_summary': None,
            'screener_results': None,
            'email_results': None,
            'workflow_success': False
        }

        try:
            # Step 1: Check if there are JSON files in output directory
            logger.info("STEP 1: Checking for JSON files in output directory")
            logger.info("-" * 50)

            json_files = self._find_json_files(output_dir)
            workflow_results['json_files_found'] = json_files

            if not json_files:
                logger.info("❌ No JSON files found in output directory - ending workflow")
                return workflow_results

            logger.info(f"✅ Found {len(json_files)} JSON file(s)")
            for file_info in json_files:
                logger.info(f"   File: {file_info['filename']} (scraped_data_id: {file_info['scraped_data_id']})")

            # Use the most recent file
            latest_file = json_files[0]
            scraped_data_id = latest_file['scraped_data_id']

            # Step 2: Get historical market data using scraped_data_id
            logger.info("STEP 2: Getting historical market data from database")
            logger.info("-" * 50)

            historical_market_data = self.db_manager.get_market_data_by_scraped_id(scraped_data_id)
            workflow_results['historical_market_data'] = historical_market_data

            if not historical_market_data:
                logger.warning(f"⚠️ No historical market data found for scraped_data_id: {scraped_data_id}")
                logger.info("Cannot proceed with market comparison - ending workflow")
                return workflow_results

            logger.info(f"✅ Found {len(historical_market_data)} historical market data points")

            # Step 3: Get current market snapshot
            logger.info("STEP 3: Capturing current market snapshot")
            logger.info("-" * 50)

            current_batch_timestamp = datetime.now()

            current_market_result = self.market_fetcher.collect_and_save_market_data_with_batch(
                scraped_data_id=None,  # Independent collection, not linked to Fed scrape
                batch_timestamp=current_batch_timestamp
            )
            current_market_data = current_market_result.get('market_data', [])

            workflow_results['current_market_data'] = current_market_data[:50]  # Limit for analysis

            logger.info(f"✅ Captured current market snapshot with {len(current_market_data)} data points")

            # Step 4: Analyze market movement
            logger.info("STEP 4: Analyzing market movement")
            logger.info("-" * 50)

            movement_analysis = self.movement_analyzer.analyze_market_movement(
                historical_market_data,
                current_market_data[:50]  # Limit for analysis
            )
            workflow_results['market_movement_analysis'] = movement_analysis

            if movement_analysis['success']:
                logger.info("✅ Market movement analysis completed")
                logger.info(f"   Commentary preview: {movement_analysis['commentary'][:100]}...")
            else:
                logger.warning(f"⚠️ Market movement analysis failed: {movement_analysis.get('error')}")

            # Step 5: Extract Fed content summary
            logger.info("STEP 5: Extracting Fed content summary")
            logger.info("-" * 50)

            fed_content_summary = self._extract_fed_content_summary(latest_file['data'])
            workflow_results['fed_content_summary'] = fed_content_summary

            logger.info(f"✅ Fed content summary extracted ({fed_content_summary['item_count']} items)")

            # Step 6: Create enhanced analysis for screener
            logger.info("STEP 6: Creating enhanced analysis for screener")
            logger.info("-" * 50)

            enhanced_analysis = self._create_enhanced_analysis(
                fed_content_summary,
                movement_analysis
            )

            # Step 7: Run screener with enhanced analysis
            logger.info("STEP 7: Running screener with enhanced analysis")
            logger.info("-" * 50)

            screener_result = self.screener_agent.create_screener_from_analysis(
                fed_analysis=enhanced_analysis
            )
            workflow_results['screener_results'] = screener_result

            if screener_result['success']:
                logger.info("✅ Screener completed successfully")
                screener_data = screener_result.get('screener_results', {})
                logger.info(f"   Total stocks found: {screener_data.get('total_results', 0)}")
                logger.info(f"   Stocks returned: {screener_data.get('returned_results', 0)}")

                # Step 8: Prepare and send email report
                logger.info("STEP 8: Preparing and sending email report")
                logger.info("-" * 50)

                email_result = self._prepare_and_send_email(
                    screener_result,
                    fed_content_summary,
                    movement_analysis
                )
                workflow_results['email_results'] = email_result

                if email_result['success']:
                    logger.info(f"✅ Email sent successfully to {len(email_result.get('recipients', []))} recipients")
                    workflow_results['workflow_success'] = True
                elif email_result.get('skipped'):
                    logger.info("📧 Email skipped - no recipients configured")
                    workflow_results['workflow_success'] = True
                else:
                    logger.error(f"❌ Email sending failed: {email_result.get('error')}")
                    # Still consider workflow successful if screener worked
                    workflow_results['workflow_success'] = True
            else:
                logger.error(f"❌ Screener failed: {screener_result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow failed: {str(e)}", exc_info=True)
            workflow_results['error'] = str(e)

        # Final Summary
        self._log_workflow_summary(workflow_results)

        return workflow_results

    def _find_json_files(self, output_dir: str) -> List[Dict[str, Any]]:
        """Find JSON files in output directory and extract scraped_data_id from filename"""

        json_files = []

        try:
            # Look for JSON files
            json_pattern = os.path.join(output_dir, "*.json")
            file_paths = glob.glob(json_pattern)

            for file_path in file_paths:
                try:
                    filename = os.path.basename(file_path)
                    # Remove .json extension to get scraped_data_id
                    scraped_data_id = os.path.splitext(filename)[0]

                    # Load and validate file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Basic validation
                    if 'timestamp' in data and 'items' in data:
                        file_info = {
                            'filename': filename,
                            'full_path': file_path,
                            'scraped_data_id': scraped_data_id,
                            'timestamp': data.get('timestamp'),
                            'data': data
                        }
                        json_files.append(file_info)

                except Exception as e:
                    logger.warning(f"Error processing file {file_path}: {e}")
                    continue

            # Sort by timestamp (newest first)
            json_files.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        except Exception as e:
            logger.error(f"Error finding JSON files: {e}")

        return json_files

    def _extract_fed_content_summary(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and summarize Fed content from JSON file"""

        items = json_data.get('items', [])

        # Create aggregated summary
        summaries = []
        sentiments = []

        for item in items:
            summary = item.get('summary', '')
            sentiment = item.get('sentiment', 'NEUTRAL')

            if summary:
                summaries.append(summary)
            if sentiment:
                sentiments.append(sentiment)

        # Aggregate sentiment
        positive_count = sum(1 for s in sentiments if s == 'POSITIVE')
        negative_count = sum(1 for s in sentiments if s == 'NEGATIVE')

        if positive_count > negative_count:
            overall_sentiment = 'POSITIVE'
        elif negative_count > positive_count:
            overall_sentiment = 'NEGATIVE'
        else:
            overall_sentiment = 'NEUTRAL'

        # Combine summaries
        aggregated_summary = " | ".join(summaries) if summaries else "No summaries available"

        return {
            'item_count': len(items),
            'aggregated_summary': aggregated_summary,
            'overall_sentiment': overall_sentiment,
            'sentiment_breakdown': {
                'positive': positive_count,
                'negative': negative_count,
                'neutral': len(sentiments) - positive_count - negative_count
            },
            'timestamp': json_data.get('timestamp'),
            'fed_items': items  # NEW: Include original items for URL extraction
        }

    def _create_enhanced_analysis(self,
                                  fed_summary: Dict[str, Any],
                                  movement_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create enhanced analysis combining Fed content and market movement"""

        # Map sentiment to market environment
        sentiment = fed_summary.get('overall_sentiment', 'NEUTRAL')

        if sentiment == 'POSITIVE':
            market_environment = 'risk_on'
            policy_stance = 'dovish'
        elif sentiment == 'NEGATIVE':
            market_environment = 'risk_off'
            policy_stance = 'hawkish'
        else:
            market_environment = 'neutral'
            policy_stance = 'neutral'

        # NEW: Create custom message for screener (replaces boring filter rationale)
        custom_message = f"""Fed Analysis + Market Movement Integration:

📊 Fed Analysis: {fed_summary['item_count']} communications, sentiment: {sentiment}

📈 Market Commentary: 
{movement_analysis.get('commentary', 'Market analysis unavailable')}

This screening integrates Fed policy signals with real-time market conditions."""

        # Create enhanced agent output
        agent_output = f"""
Enhanced Fed Analysis with Market Movement Integration:

Fed Content Analysis:
- Analyzed {fed_summary['item_count']} Federal Reserve communications
- Overall sentiment: {sentiment}
- Policy stance assessment: {policy_stance}

Fed Content Summary:
{fed_summary['aggregated_summary'][:1000]}{'...' if len(fed_summary['aggregated_summary']) > 1000 else ''}

Market Movement Analysis:
{movement_analysis.get('commentary', 'Market analysis unavailable')}

Screening Strategy:
Based on Fed communications sentiment ({sentiment}) and current market conditions, 
optimizing screening for {market_environment} environment with {policy_stance} policy expectations.
        """.strip()

        return {
            'analysis_result': {
                'market_environment': market_environment,
                'policy_stance': policy_stance,
                'risk_sentiment': market_environment,
                'fed_summary': fed_summary,
                'market_analysis': movement_analysis,
                'enhanced': True
            },
            'screening_needed': True,
            'agent_output': agent_output,
            'custom_message': custom_message,  # NEW: For screener to use as rationale
            'execution_id': f"enhanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }

    def _prepare_and_send_email(self,
                                screener_result: Dict[str, Any],
                                fed_summary: Dict[str, Any],
                                movement_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Send email using existing email agent with enhanced content"""

        try:
            # Check recipients
            recipient_emails_str = os.getenv('RECIPIENT_EMAILS', '')
            if not recipient_emails_str:
                return {'success': False, 'skipped': True, 'reason': 'No recipients configured'}

            recipient_emails = [email.strip() for email in recipient_emails_str.split(',')]

            # Get screener result ID
            screener_data = screener_result.get('screener_results', {})
            screener_result_id = screener_data.get('tradingview_data', {}).get('screener_result_id')

            if not screener_result_id:
                raise ValueError("No screener result ID found")

            # NEW: Create enhanced message with Fed URLs and full market commentary
            fed_items = fed_summary.get('fed_items', [])  # Get original Fed items
            fed_urls = []
            if fed_items:
                for item in fed_items[:5]:  # Top 5 URLs
                    url = item.get('url', '')
                    title = item.get('title', 'Fed Communication')[:60]
                    if url:
                        fed_urls.append(f"• {title}: {url}")

            market_commentary = movement_analysis.get('commentary', 'Market analysis unavailable')

            custom_message = f"""Fed Analysis + Market Movement Integration:

📊 Fed Analysis: {fed_summary.get('item_count', 0)} communications, sentiment: {fed_summary.get('overall_sentiment', 'NEUTRAL')}

📈 Market Commentary: 
{market_commentary}

🏛️ Fed Source Documents:
{chr(10).join(fed_urls) if fed_urls else 'No Fed URLs available'}

This screening integrates Fed policy signals with real-time market data analysis."""

            # Use existing email agent
            from agents.email_agent import send_screener_email

            email_result = send_screener_email(
                db_manager=self.db_manager,
                screener_result_id=screener_result_id,
                recipient_emails=recipient_emails,
                custom_message=custom_message
            )

            if email_result['success']:
                email_result['recipients'] = recipient_emails

            return email_result

        except Exception as e:
            logger.error(f"Email error: {e}")
            return {'success': False, 'error': str(e)}

    def _log_workflow_summary(self, workflow_results: Dict[str, Any]):
        """Log workflow summary"""

        logger.info("=" * 80)
        logger.info("ENHANCED WORKFLOW SUMMARY")
        logger.info("=" * 80)

        json_files = workflow_results.get('json_files_found', [])
        logger.info(f"JSON Files Found: {len(json_files)}")

        historical_data = workflow_results.get('historical_market_data', [])
        logger.info(f"Historical Market Data: {len(historical_data) if historical_data else 0} points")

        current_data = workflow_results.get('current_market_data', [])
        logger.info(f"Current Market Data: {len(current_data) if current_data else 0} points")

        movement_analysis = workflow_results.get('market_movement_analysis', {})
        logger.info(f"Market Movement Analysis: {'✅ SUCCESS' if movement_analysis.get('success') else '❌ FAILED'}")

        fed_summary = workflow_results.get('fed_content_summary', {})
        logger.info(f"Fed Content Summary: {fed_summary.get('item_count', 0) if fed_summary else 0} items")

        screener_results = workflow_results.get('screener_results', {})
        logger.info(f"Screener Results: {'✅ SUCCESS' if screener_results.get('success') else '❌ FAILED'}")

        email_results = workflow_results.get('email_results', {})
        if email_results:
            if email_results.get('skipped'):
                logger.info("Email Report: 📧 SKIPPED (no recipients)")
            else:
                logger.info(f"Email Report: {'✅ SUCCESS' if email_results.get('success') else '❌ FAILED'}")
        else:
            logger.info("Email Report: ❌ NOT ATTEMPTED")

        logger.info(f"Overall Success: {'✅ YES' if workflow_results.get('workflow_success') else '❌ NO'}")
        logger.info("=" * 80)
        """Log workflow summary"""

        logger.info("=" * 80)
        logger.info("ENHANCED WORKFLOW SUMMARY")
        logger.info("=" * 80)

        json_files = workflow_results.get('json_files_found', [])
        logger.info(f"JSON Files Found: {len(json_files)}")

        historical_data = workflow_results.get('historical_market_data', [])
        logger.info(f"Historical Market Data: {len(historical_data) if historical_data else 0} points")

        current_data = workflow_results.get('current_market_data', [])
        logger.info(f"Current Market Data: {len(current_data) if current_data else 0} points")

        movement_analysis = workflow_results.get('market_movement_analysis', {})
        logger.info(f"Market Movement Analysis: {'✅ SUCCESS' if movement_analysis.get('success') else '❌ FAILED'}")

        fed_summary = workflow_results.get('fed_content_summary', {})
        logger.info(f"Fed Content Summary: {fed_summary.get('item_count', 0) if fed_summary else 0} items")

        screener_results = workflow_results.get('screener_results', {})
        logger.info(f"Screener Results: {'✅ SUCCESS' if screener_results.get('success') else '❌ FAILED'}")

        email_results = workflow_results.get('email_results', {})
        if email_results:
            if email_results.get('skipped'):
                logger.info("Email Report: 📧 SKIPPED (no recipients)")
            else:
                logger.info(f"Email Report: {'✅ SUCCESS' if email_results.get('success') else '❌ FAILED'}")
        else:
            logger.info("Email Report: ❌ NOT ATTEMPTED")

        logger.info(f"Overall Success: {'✅ YES' if workflow_results.get('workflow_success') else '❌ NO'}")
        logger.info("=" * 80)