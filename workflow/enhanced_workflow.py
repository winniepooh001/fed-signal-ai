import glob
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.filter_decision import FilterDecisionAgent
from agents.market_movement_analyzer import MarketMovementAnalyzer
from agents.screener_analysis_agent import ScreenerAnalysisAgent
from database.database import DatabaseManager
from market_data.data_fetch import DatabaseIntegratedMarketDataFetcher
from utils.logging_config import get_logger

logger = get_logger(__name__)


class EnhancedMainAgent:
    """Main agent with corrected market integration logic"""

    def __init__(
        self,
        database_url: str = "sqlite:///screener_data.db",
        model: str = "gpt-4o-mini",
    ):
        self.database_url = database_url
        self.db_manager = DatabaseManager(database_url)
        self.db_manager.create_tables()

        # Initialize market fetcher for current snapshot
        self.market_fetcher = DatabaseIntegratedMarketDataFetcher(database_url)

        # Initialize market movement analyzer
        self.movement_analyzer = MarketMovementAnalyzer(model=model)

        # Initialize filter decision agent
        self.filter_decision_agent = FilterDecisionAgent(model=model)

        # Initialize screener agent
        self.screener_agent = ScreenerAnalysisAgent(
            database_url=database_url, model=model, temperature=0
        )

        logger.info("Enhanced Main Agent initialized with smart filtering")

    def _get_most_recent_filter(self) -> Optional[Dict[str, Any]]:
        """Get the most recent successful screener execution"""

        try:
            with self.db_manager.get_session() as session:
                from database.models import (
                    AgentExecution,
                    ScreenerInput,
                    ScreenerResult,
                )

                # Get most recent successful screener execution
                recent_execution = (
                    session.query(AgentExecution)
                    .join(ScreenerInput)
                    .join(ScreenerResult)
                    .filter(AgentExecution.success == True)
                    .filter(ScreenerResult.success == True)
                    .order_by(AgentExecution.completed_at.desc())
                    .first()
                )

                if not recent_execution:
                    return None

                # Extract metadata from execution
                metadata = {}
                if recent_execution.execution_metadata:
                    try:
                        metadata = json.loads(recent_execution.execution_metadata)
                    except:
                        pass

                return {
                    "execution_id": recent_execution.id,
                    "timestamp": recent_execution.completed_at.isoformat(),
                    "fed_item_count": metadata.get("fed_item_count", 0),
                    "fed_sentiment": metadata.get("fed_sentiment", "UNKNOWN"),
                    "market_condition": metadata.get("market_condition", "UNKNOWN"),
                    "user_prompt": recent_execution.user_prompt[:200],
                    "days_ago": (
                        datetime.utcnow() - recent_execution.completed_at
                    ).days,
                }

        except Exception as e:
            logger.error(f"Error getting recent filter: {e}")
            return None

    def run_workflow(self, output_dir: str = "output") -> Dict[str, Any]:
        """
        Run the corrected workflow

        Args:
            output_dir: Directory to check for JSON files

        Returns:
            Dict with workflow results
        """

        logger.info("=" * 80)
        logger.info("STARTING SMART FILTERING WORKFLOW")
        logger.info("=" * 80)

        workflow_results = {
            "json_files_found": [],
            "historical_market_data": None,
            "current_market_data": None,
            "market_movement_analysis": None,
            "fed_content_summary": None,
            "most_recent_filter": None,
            "filter_decision": None,
            "screener_results": None,
            "email_results": None,
            "fed_content_saved": None,
            "workflow_success": False,
            "exit_reason": None,
        }

        try:
            # Step 1: Check if there are JSON files in output directory
            logger.info("STEP 1: Checking for JSON files in output directory")
            logger.info("-" * 50)

            json_files = self._find_json_files(output_dir)
            workflow_results["json_files_found"] = json_files

            if not json_files:
                logger.info(
                    "❌ No JSON files found in output directory - ending workflow"
                )
                return workflow_results

            logger.info(f"✅ Found {len(json_files)} JSON file(s)")
            for file_info in json_files:
                logger.info(
                    f"   File: {file_info['filename']} (scraped_data_id: {file_info['scraped_data_id']})"
                )

            # Use the most recent file
            latest_file = json_files[0]
            scraped_data_id = latest_file["scraped_data_id"]

            # Step 2: Get historical market data using scraped_data_id
            logger.info("STEP 2: Getting historical market data from database")
            logger.info("-" * 50)

            historical_market_data = self.db_manager.get_market_data_by_scraped_id(
                scraped_data_id
            )
            workflow_results["historical_market_data"] = historical_market_data

            if not historical_market_data:
                logger.warning(
                    f"⚠️ No historical market data found for scraped_data_id: {scraped_data_id}"
                )
                logger.info("Cannot proceed with market comparison - ending workflow")
                return workflow_results

            logger.info(
                f"✅ Found {len(historical_market_data)} historical market data points"
            )

            # Step 3: Get current market snapshot
            logger.info("STEP 3: Capturing current market snapshot")
            logger.info("-" * 50)

            current_batch_timestamp = datetime.now()

            current_market_result = self.market_fetcher.collect_and_save_market_data_with_batch(
                scraped_data_id=None,  # Independent collection, not linked to Fed scrape
                batch_timestamp=current_batch_timestamp,
            )
            current_market_data = current_market_result.get("market_data", [])

            workflow_results["current_market_data"] = current_market_data[
                :50
            ]  # Limit for analysis

            logger.info(
                f"✅ Captured current market snapshot with {len(current_market_data)} data points"
            )

            # Step 4: Analyze market movement
            logger.info("STEP 4: Analyzing market movement")
            logger.info("-" * 50)

            movement_analysis = self.movement_analyzer.analyze_market_movement(
                historical_market_data, current_market_data[:50]  # Limit for analysis
            )
            workflow_results["market_movement_analysis"] = movement_analysis

            if movement_analysis["success"]:
                logger.info("✅ Market movement analysis completed")
                logger.info(
                    f"   Commentary preview: {movement_analysis['commentary'][:100]}..."
                )
            else:
                logger.warning(
                    f"⚠️ Market movement analysis failed: {movement_analysis.get('error')}"
                )

            # Step 5: Extract Fed content summary
            logger.info("STEP 5: Extracting Fed content summary")
            logger.info("-" * 50)

            fed_content_summary = self._extract_fed_content_summary(latest_file["data"])
            workflow_results["fed_content_summary"] = fed_content_summary

            logger.info(
                f"✅ Fed content summary extracted ({fed_content_summary['item_count']} items)"
            )
            # step 6
            logger.info("STEP 6: Checking if new filtering is warranted")
            logger.info("-" * 50)

            most_recent_filter = self._get_most_recent_filter()
            workflow_results["most_recent_filter"] = most_recent_filter

            if most_recent_filter:
                logger.info(
                    f"Found recent filter from {most_recent_filter['days_ago']} days ago"
                )
                logger.info(
                    f"Recent filter: {most_recent_filter['fed_sentiment']} sentiment, {most_recent_filter['fed_item_count']} Fed items"
                )

                # Ask LLM if new filter is warranted
                filter_decision = self.filter_decision_agent.should_create_new_filter(
                    most_recent_filter, fed_content_summary, movement_analysis
                )
                workflow_results["filter_decision"] = filter_decision

                if not filter_decision["create_new_filter"]:
                    logger.info("🚫 NEW FILTERING NOT WARRANTED")
                    logger.info(f"Reason: {filter_decision['reasoning'][:200]}...")
                    workflow_results["workflow_success"] = True
                    workflow_results["exit_reason"] = "Recent filter still relevant"
                    should_run_screening = False  # Don't run screening

                else:
                    logger.info("✅ NEW FILTERING WARRANTED")
                    logger.info(f"Reason: {filter_decision['reasoning'][:200]}...")
                    should_run_screening = True  # Run screening

            else:
                logger.info("No recent filter found - proceeding with new screening")
                workflow_results["filter_decision"] = {
                    "create_new_filter": True,
                    "reasoning": "No recent filter found",
                }
                should_run_screening = True  # Run screening

            should_run_screening = True
            # Only run Steps 7-8 if screening is warranted
            if should_run_screening:
                # Step 7: Create enhanced analysis for screener
                logger.info("STEP 7: Creating enhanced analysis for screener")
                logger.info("-" * 50)

                enhanced_analysis = self._create_enhanced_analysis(
                    fed_content_summary, movement_analysis
                )

                # Add metadata for future filter decisions
                enhanced_analysis["metadata"] = {
                    "fed_item_count": fed_content_summary.get("item_count", 0),
                    "fed_sentiment": fed_content_summary.get(
                        "overall_sentiment", "NEUTRAL"
                    ),
                    "market_condition": "enhanced_analysis",
                }

                # Step 8: Run screener with enhanced analysis
                logger.info("STEP 8: Running screener with enhanced analysis")
                logger.info("-" * 50)

                screener_result = self.screener_agent.create_screener_from_analysis(
                    fed_analysis=enhanced_analysis
                )
                workflow_results["screener_results"] = screener_result

                if screener_result["success"]:
                    logger.info("✅ Screener completed successfully")
                    screener_data = screener_result.get("screener_results", {})
                    logger.info(
                        f"   Total stocks found: {screener_data.get('total_results', 0)}"
                    )
                    logger.info(
                        f"   Stocks returned: {screener_data.get('returned_results', 0)}"
                    )

                    # Update execution metadata with filter info for future decisions
                    self._update_execution_metadata(
                        screener_result.get("execution_id"),
                        enhanced_analysis.get("metadata", {}),
                    )

                    # Step 9: Prepare and send email report
                    logger.info("STEP 9: Preparing and sending email report")
                    logger.info("-" * 50)

                    email_result = self._prepare_and_send_email(
                        screener_result, fed_content_summary, movement_analysis
                    )
                    workflow_results["email_results"] = email_result

                    if email_result["success"]:
                        logger.info(
                            f"✅ Email sent successfully to {len(email_result.get('recipients', []))} recipients"
                        )
                        workflow_results["workflow_success"] = True
                    elif email_result.get("skipped"):
                        logger.info("📧 Email skipped - no recipients configured")
                        workflow_results["workflow_success"] = True
                    else:
                        logger.error(
                            f"❌ Email sending failed: {email_result.get('error')}"
                        )
                        workflow_results["workflow_success"] = True
                else:
                    logger.error(f"❌ Screener failed: {screener_result.get('error')}")

            else:
                # Screening not warranted - exit successfully without running steps 7-8
                logger.info("Skipping screening steps 7-8 - not warranted")
                workflow_results["workflow_success"] = True

        except Exception as e:
            logger.error(f"Workflow failed: {str(e)}", exc_info=True)
            workflow_results["error"] = str(e)

        # Final Summary
        self._log_workflow_summary(workflow_results)

        return workflow_results

    def _update_execution_metadata(self, execution_id: str, metadata: Dict[str, Any]):
        """Update execution metadata for future filter decisions"""

        try:
            with self.db_manager.get_session() as session:
                from database.models import AgentExecution

                execution = (
                    session.query(AgentExecution).filter_by(id=execution_id).first()
                )
                if execution:
                    current_metadata = {}
                    if execution.execution_metadata:
                        try:
                            current_metadata = json.loads(execution.execution_metadata)
                        except:
                            pass

                    # Update with new metadata
                    current_metadata.update(metadata)
                    execution.execution_metadata = json.dumps(current_metadata)

                    logger.debug(f"Updated execution {execution_id} metadata")

        except Exception as e:
            logger.error(f"Error updating execution metadata: {e}")

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
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Basic validation
                    if "timestamp" in data and "items" in data:
                        file_info = {
                            "filename": filename,
                            "full_path": file_path,
                            "scraped_data_id": scraped_data_id,
                            "timestamp": data.get("timestamp"),
                            "data": data,
                        }
                        json_files.append(file_info)

                except Exception as e:
                    logger.warning(f"Error processing file {file_path}: {e}")
                    continue

            # Sort by timestamp (newest first)
            json_files.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        except Exception as e:
            logger.error(f"Error finding JSON files: {e}")

        return json_files

    def _extract_fed_content_summary(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and summarize Fed content from JSON file"""

        items = json_data.get("items", [])

        # Create aggregated summary
        summaries = []
        sentiments = []

        for item in items:
            summary = item.get("summary", "")
            sentiment = item.get("sentiment", "NEUTRAL")

            if summary:
                summaries.append(summary)
            if sentiment:
                sentiments.append(sentiment)

        # Aggregate sentiment
        positive_count = sum(1 for s in sentiments if s == "POSITIVE")
        negative_count = sum(1 for s in sentiments if s == "NEGATIVE")

        if positive_count > negative_count:
            overall_sentiment = "POSITIVE"
        elif negative_count > positive_count:
            overall_sentiment = "NEGATIVE"
        else:
            overall_sentiment = "NEUTRAL"

        # Combine summaries
        aggregated_summary = (
            " | ".join(summaries) if summaries else "No summaries available"
        )

        return {
            "item_count": len(items),
            "aggregated_summary": aggregated_summary,
            "overall_sentiment": overall_sentiment,
            "sentiment_breakdown": {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": len(sentiments) - positive_count - negative_count,
            },
            "timestamp": json_data.get("timestamp"),
            "fed_items": items,  # NEW: Include original items for URL extraction
        }

    def _create_enhanced_analysis(
        self, fed_summary: Dict[str, Any], movement_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create enhanced analysis combining Fed content and market movement"""

        # Map sentiment to market environment
        sentiment = fed_summary.get("overall_sentiment", "NEUTRAL")

        if sentiment == "POSITIVE":
            market_environment = "risk_on"
            policy_stance = "dovish"
        elif sentiment == "NEGATIVE":
            market_environment = "risk_off"
            policy_stance = "hawkish"
        else:
            market_environment = "neutral"
            policy_stance = "neutral"

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
            "analysis_result": {
                "market_environment": market_environment,
                "policy_stance": policy_stance,
                "risk_sentiment": market_environment,
                "fed_summary": fed_summary,
                "market_analysis": movement_analysis,
                "enhanced": True,
            },
            "screening_needed": True,
            "agent_output": agent_output,
            "custom_message": custom_message,  # NEW: For screener to use as rationale
            "execution_id": f"enhanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        }

    # workflow/enhanced_workflow.py - Updated _prepare_and_send_email method

    def _prepare_and_send_email(
        self,
        screener_result: Dict[str, Any],
        fed_summary: Dict[str, Any],
        movement_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send email using existing email agent with enhanced content"""

        try:
            # Check recipients
            recipient_emails_str = os.getenv("RECIPIENT_EMAILS", "")
            if not recipient_emails_str:
                return {
                    "success": False,
                    "skipped": True,
                    "reason": "No recipients configured",
                }

            recipient_emails = [
                email.strip() for email in recipient_emails_str.split(",")
            ]

            # Get screener result ID
            screener_data = screener_result.get("screener_results", {})
            screener_result_id = screener_data.get("tradingview_data", {}).get(
                "screener_result_id"
            )

            if not screener_result_id:
                raise ValueError("No screener result ID found")

            # Create structured custom message for email
            fed_items = fed_summary.get("fed_items", [])

            # Fed Analysis Summary
            fed_analysis_section = f"""Fed Analysis Summary
    Analyzed {fed_summary.get('item_count', 0)} Federal Reserve communications with overall sentiment: {fed_summary.get('overall_sentiment', 'NEUTRAL')}
    \n
    Key Fed Content: {fed_summary.get('aggregated_summary', 'No summary available')}"""

            # Market Movement Analysis
            market_commentary = movement_analysis.get(
                "commentary", "Market analysis unavailable"
            )
            market_section = f"""Market Movement Analysis
    {market_commentary}"""

            # Fed Source Documents
            fed_sources_section = ""
            if fed_items:
                fed_sources_section = "Fed Source Documents\n"
                for item in fed_items[:5]:  # Top 5 URLs
                    url = item.get("url", "")
                    title = item.get("title", "Fed Communication")[:80]
                    if url:
                        fed_sources_section += f"\n\n {title}: {url}\n"

            # Screening Strategy
            strategy_section = f"""Screening Strategy
    This screening integrates Federal Reserve policy signals with real-time market data analysis to identify stocks positioned for current market conditions. The filter criteria reflect the {fed_summary.get('overall_sentiment', 'neutral')} Fed sentiment and observed market movements."""

            # Combine all sections with clear separators
            custom_message_parts = [
                fed_analysis_section,
                market_section,
                fed_sources_section.strip() if fed_sources_section else None,
                strategy_section,
            ]

            # Join non-empty sections
            custom_message = "\n\n".join(part for part in custom_message_parts if part)

            # Use existing email agent
            from agents.email_agent import send_screener_email

            email_result = send_screener_email(
                db_manager=self.db_manager,
                screener_result_id=screener_result_id,
                recipient_emails=recipient_emails,
                custom_message=custom_message,
            )

            if email_result["success"]:
                email_result["recipients"] = recipient_emails

            return email_result

        except Exception as e:
            logger.error(f"Email error: {e}")
            return {"success": False, "error": str(e)}

    def _log_workflow_summary(self, workflow_results: Dict[str, Any]):
        """Updated log workflow summary with null safety"""

        logger.info("=" * 80)
        logger.info("SMART FILTERING WORKFLOW SUMMARY")
        logger.info("=" * 80)

        json_files = workflow_results.get("json_files_found", [])
        logger.info(f"JSON Files Found: {len(json_files)}")

        historical_data = workflow_results.get("historical_market_data", [])
        logger.info(
            f"Historical Market Data: {len(historical_data) if historical_data else 0} points"
        )

        current_data = workflow_results.get("current_market_data", [])
        logger.info(
            f"Current Market Data: {len(current_data) if current_data else 0} points"
        )

        movement_analysis = workflow_results.get("market_movement_analysis", {})
        logger.info(
            f"Market Movement Analysis: {'✅ SUCCESS' if movement_analysis and movement_analysis.get('success') else '❌ FAILED'}"
        )

        fed_summary = workflow_results.get("fed_content_summary", {})
        logger.info(
            f"Fed Content Summary: {fed_summary.get('item_count', 0) if fed_summary else 0} items"
        )

        # FIX: Add null safety for recent filter and filter decision
        recent_filter = workflow_results.get("most_recent_filter")
        if recent_filter:
            logger.info(
                f"Recent Filter: {recent_filter['days_ago']} days ago ({recent_filter['fed_sentiment']})"
            )
        else:
            logger.info("Recent Filter: None found")

        filter_decision = workflow_results.get("filter_decision")
        if filter_decision:
            decision = (
                "✅ CREATE NEW"
                if filter_decision.get("create_new_filter")
                else "🚫 SKIP (RECENT EXISTS)"
            )
            logger.info(f"Filter Decision: {decision}")

        # FIX: Add null safety for screener results
        screener_results = workflow_results.get("screener_results")
        if screener_results:
            logger.info(
                f"Screener Results: {'✅ SUCCESS' if screener_results.get('success') else '❌ FAILED'}"
            )
        else:
            logger.info("Screener Results: ❌ NOT EXECUTED")

        email_results = workflow_results.get("email_results")
        if email_results:
            if email_results.get("skipped"):
                logger.info("Email Report: 📧 SKIPPED (no recipients)")
            else:
                logger.info(
                    f"Email Report: {'✅ SUCCESS' if email_results.get('success') else '❌ FAILED'}"
                )
        else:
            logger.info("Email Report: ❌ NOT ATTEMPTED")

        fed_saved = workflow_results.get("fed_content_saved")
        if fed_saved:
            logger.info(
                f"Fed Content Saved: {'✅ SUCCESS' if fed_saved.get('success') else '❌ FAILED'} ({fed_saved.get('saved_count', 0)} items)"
            )
        else:
            logger.info("Fed Content Saved: ❌ NOT ATTEMPTED")

        exit_reason = workflow_results.get("exit_reason")
        if exit_reason:
            logger.info(f"Exit Reason: {exit_reason}")

        logger.info(
            f"Overall Success: {'✅ YES' if workflow_results.get('workflow_success') else '❌ NO'}"
        )
        logger.info("=" * 80)
