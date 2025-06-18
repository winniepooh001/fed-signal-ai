from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.schema.runnable import RunnableConfig
from typing import Dict, Any, Optional
from datetime import datetime
import json

from database import DatabaseManager
from agents.prompts import SCREENER_ANALYSIS_AGENT_PROMPT
from utils.llm_callback import UniversalLLMUsageTracker
from utils.llm_provider import create_llm
from utils.logging_config import get_logger
from tools.tradingview_query import TradingViewQueryTool

# Get module-specific logger
logger = get_logger('screener_analysis_agent')


class ScreenerAnalysisAgent:
    """Agent specifically for creating and executing stock screeners based on analysis input"""

    def __init__(self,
                 database_url: str,
                 model: str = "gpt-4o-mini",  # Now supports any provider
                 provider: Optional[str] = None,  # Optional explicit provider
                 tradingview_cookies: Optional[Dict] = None,
                 temperature: float = 0.1,
                 max_iterations: int = 2):
        """Initialize Screener analysis agent"""

        logger.info("Initializing ScreenerAnalysisAgent")
        logger.debug(f"Configuration: model={model}, temperature={temperature}")

        # Initialize database manager
        logger.info("Setting up database manager")
        self.db_manager = DatabaseManager(database_url)

        # Create tables if they don't exist
        logger.debug("Creating database tables if they don't exist")
        self.db_manager.create_tables()

        # Initialize LLM
        logger.info(f"Initializing LLM with model: {model}")
        self.llm = create_llm(
            model=model,
            provider=provider,
            temperature=temperature
        )
        logger.info(f"LLM created successfully: {type(self.llm).__name__}")

        # Initialize tools - only TradingView tool for this agent
        logger.info("Setting up screener execution tools")
        self.tools = [
            TradingViewQueryTool(
                db_manager=self.db_manager,
                cookies=tradingview_cookies
            )
        ]
        logger.debug(f"Initialized {len(self.tools)} tools for screener execution")

        # Create agent
        logger.debug("Creating screener analysis agent")
        self.agent = create_openai_tools_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=SCREENER_ANALYSIS_AGENT_PROMPT
        )

        # Create executor
        logger.debug("Creating screener analysis agent executor")
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            max_iterations=max_iterations,
            return_intermediate_steps=True
        )

        logger.info("ScreenerAnalysisAgent initialization completed successfully")

    def create_screener_from_analysis(self,
                                      fed_analysis: Dict[str, Any],
                                      custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Create and execute screener based on Fed analysis or custom prompt

        Args:
            fed_analysis: Result from FedAnalysisAgent
            custom_prompt: Optional custom analysis prompt

        Returns:
            Dict containing:
            - success: bool
            - screener_results: dict with TradingView results
            - execution_id: str
            - llm_usage: dict
        """

        logger.info("Starting screener creation and execution")

        # Determine execution type and input
        if custom_prompt:
            execution_type = "custom_screener"
            analysis_input = custom_prompt
            logger.info("Using custom prompt for screener creation")
        else:
            execution_type = "fed_based_screener"
            analysis_input = f"Fed analysis: {fed_analysis.get('analysis_result', {})}"
            logger.info("Using Fed analysis for screener creation")

        # Start agent execution tracking
        execution_id = self.db_manager.start_agent_execution(
            user_prompt=analysis_input[:500],  # Truncate for storage
            execution_type=execution_type,
            metadata={
                'fed_analysis_id': fed_analysis.get('execution_id') if fed_analysis else None,
                'has_custom_prompt': bool(custom_prompt)
            }
        )

        logger.info(f"Started screener execution tracking with ID: {execution_id}")

        # Initialize LLM tracker for this execution
        llm_tracker = UniversalLLMUsageTracker(self.db_manager, execution_id)

        # Set execution ID for tools to use
        for tool in self.tools:
            if hasattr(tool, 'set_execution_id'):
                tool.set_execution_id(execution_id)

        # Create screening prompt based on input type
        if custom_prompt:
            prompt = self._create_custom_screener_prompt(custom_prompt)
        else:
            prompt = self._create_fed_based_screener_prompt(fed_analysis)

        try:
            logger.info("Executing screener analysis agent")
            # Execute agent with tracking callback
            config = RunnableConfig(callbacks=[llm_tracker])
            result = self.agent_executor.invoke({"input": prompt}, config=config)

            logger.info("Screener analysis agent execution completed successfully")

            # Parse screener results from agent output and intermediate steps
            screener_results = self._extract_screener_results(result)

            # Get LLM usage stats for this execution
            logger.debug("Retrieving LLM usage statistics")
            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)

            # Complete the execution tracking
            logger.debug("Completing screener execution tracking")
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=result.get('output', ''),
                success=True
            )

            logger.info(f"Screener creation completed successfully")
            logger.info(f"LLM cost: ${llm_stats['total_cost']:.4f}")

            return {
                'success': True,
                'execution_id': execution_id,
                'screener_results': screener_results,
                'agent_output': result.get('output', ''),
                'intermediate_steps': result.get('intermediate_steps', []),
                'llm_usage': llm_stats,
                'execution_type': execution_type,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Screener creation failed: {str(e)}", exc_info=True)

            # Get partial LLM usage stats even on error
            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)

            # Complete execution with error
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=f"Error during screener creation: {str(e)}",
                success=False,
                error_message=str(e)
            )

            logger.warning(f"LLM costs incurred despite error: ${llm_stats['total_cost']:.4f}")

            return {
                'success': False,
                'execution_id': execution_id,
                'error': str(e),
                'llm_usage': llm_stats,
                'execution_type': execution_type,
                'timestamp': datetime.now().isoformat()
            }

    def _create_fed_based_screener_prompt(self, fed_analysis: Dict[str, Any]) -> str:
        """Create screening prompt based on Fed analysis results"""

        logger.debug("Creating Fed-based screener prompt")

        analysis_result = fed_analysis.get('analysis_result', {})
        market_environment = analysis_result.get('market_environment', 'neutral')
        policy_stance = analysis_result.get('policy_stance', 'neutral')
        risk_sentiment = analysis_result.get('movement_analysis', 'neutral')
        fed_summary = analysis_result.get('fed_summary', '')

        prompt = f"""
        Based on the Federal Reserve analysis, create an appropriate stock screener for the current market environment.

        Fed Analysis Summary:
        - Market Environment: {market_environment}
        - Policy Stance: {policy_stance}
        - Movement Since News: {risk_sentiment}
        - Fed Summary: {fed_summary}
        - Analysis Output: {fed_analysis.get('agent_output', '')[:500]}...

        Create ONE TradingView screener that aligns with this Fed analysis by applying appropriate filters 

        Execute the tradingview_query tool with appropriate filters to target 20-50 stocks.
        Provide reasoning for your filter choices based on the Fed analysis.
        
        STOP AFTER FIRST TOOL CALL - Never call tradingview_query multiple times!

        Example workflow:
        - User asks for screener
        - You think: "I need momentum stocks with high volume"
        - You call tradingview_query ONCE with filters
        - You get results
        - You say: "Here are the results from the screener: [summary]"
        - DONE - No more tool calls
        """

        return prompt

    def _create_custom_screener_prompt(self, custom_prompt: str) -> str:
        """Create screening prompt based on custom input"""

        logger.debug("Creating custom screener prompt")

        prompt = f"""
        Based on the following analysis or market conditions, create an appropriate stock screener.

        Analysis/Request: {custom_prompt}

        Create ONE TradingView screener that addresses this analysis or request.

        Guidelines:
        - Focus on actively traded US stocks with sufficient liquidity
        - Target 20-50 stocks in your results
        - Use at most 5 filters to keep the screener focused
        - Provide clear reasoning for your filter choices

        Execute the tradingview_query tool with appropriate filters.
        """

        return prompt

    def _extract_screener_results(self, agent_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and parse screener results from agent execution"""

        logger.debug("Extracting screener results from agent output")

        screener_data = {
            'filters_used': [],
            'total_results': 0,
            'returned_results': 0,
            'sample_stocks': [],
            'execution_time_ms': 0,
            'reasoning': '',
            'tradingview_data': None
        }

        # Extract from intermediate steps (tool calls)
        intermediate_steps = agent_result.get('intermediate_steps', [])

        for step in intermediate_steps:
            if len(step) >= 2:
                action, observation = step[0], step[1]

                # Check if this was a TradingView tool call
                if hasattr(action, 'tool') and action.tool == 'tradingview_query':
                    logger.debug("Found TradingView tool execution in intermediate steps")

                    try:
                        # Parse the observation (tool result)
                        if isinstance(observation, str):
                            tool_result = json.loads(observation)
                            screener_data['tradingview_data'] = tool_result
                            screener_data['total_results'] = tool_result.get('total_results', 0)
                            screener_data['returned_results'] = tool_result.get('returned_results', 0)
                            screener_data['execution_time_ms'] = tool_result.get('execution_time_ms', 0)
                            screener_data['sample_stocks'] = tool_result.get('data_preview', [])[:5]
                            screener_data['filters_used'] = tool_result.get('filters_applied', [])

                            logger.debug(f"Extracted screener results: {screener_data['total_results']} total stocks")

                    except json.JSONDecodeError as e:
                        logger.warning(f"Could not parse TradingView tool result: {e}")

        # Extract reasoning from agent output
        agent_output = agent_result.get('output', '')
        screener_data['reasoning'] = agent_output[:500] if agent_output else 'No reasoning provided'

        return screener_data

    def get_screener_history(self, limit: int = 10) -> list:
        """Get recent screener execution history"""
        logger.debug(f"Retrieving screener execution history (limit: {limit})")

        try:
            with self.db_manager.get_session() as session:
                from database.models import AgentExecution

                executions = session.query(AgentExecution) \
                    .filter(AgentExecution.execution_type.in_(['fed_based_screener', 'custom_screener'])) \
                    .order_by(AgentExecution.started_at.desc()) \
                    .limit(limit).all()

                history = [
                    {
                        'id': str(exec.id),
                        'execution_type': exec.execution_type,
                        'user_prompt': exec.user_prompt[:200] + '...' if len(
                            exec.user_prompt) > 200 else exec.user_prompt,
                        'success': exec.success,
                        'started_at': exec.started_at.isoformat(),
                        'completed_at': exec.completed_at.isoformat() if exec.completed_at else None
                    }
                    for exec in executions
                ]

                logger.debug(f"Retrieved {len(history)} screener execution records")
                return history

        except Exception as e:
            logger.error(f"Error getting screener execution history: {e}")
            return []

    def get_screener_results_by_execution(self, execution_id: str) -> list:
        """Get all screener results for a specific execution"""
        logger.debug(f"Retrieving screener results for execution: {execution_id}")

        try:
            with self.db_manager.get_session() as session:
                from database.models import ScreenerResult, ScreenerInput

                results = session.query(ScreenerResult) \
                    .join(ScreenerInput) \
                    .filter(ScreenerInput.agent_execution_id == execution_id) \
                    .all()

                screener_results = [
                    {
                        'result_id': str(result.id),
                        'input_id': str(result.screener_input_id),
                        'total_results': result.total_results,
                        'returned_results': result.returned_results,
                        'success': result.success,
                        'executed_at': result.query_executed_at.isoformat(),
                        'execution_time_ms': result.execution_time_ms,
                        'data_preview': json.loads(result.result_data)[:5] if result.result_data else []
                    }
                    for result in results
                ]

                logger.debug(f"Retrieved {len(screener_results)} screener results")
                return screener_results

        except Exception as e:
            logger.error(f"Error getting screener results: {e}")
            return []