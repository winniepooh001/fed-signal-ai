from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from langchain.schema.runnable import RunnableConfig
from typing import Dict, Any, Optional
from datetime import datetime
import json

from database import DatabaseManager, EmbeddingManager
from agents.prompts import FED_ANALYSIS_AGENT_PROMPT
from utils.llm_callback import UniversalLLMUsageTracker
from utils.logging_config import get_logger
from tools.fed_scraper import FedWebScraperTool
from utils.llm_provider import create_llm  # NEW: Use LLM factory
# Get module-specific logger
logger = get_logger()


class FedAnalysisAgent:
    """Agent specifically for Fed data analysis and screening decision-making"""

    def __init__(self,
                 database_url: str,
                 model: str = "gpt-4o-mini",  # Now supports any provider
                 provider: Optional[str] = None,  # Optional explicit provider
                 embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
                 temperature: float = 0.1,
                 max_iterations: int = 3):
        """Initialize Fed analysis agent"""

        logger.info("Initializing FedAnalysisAgent")
        logger.debug(f"Configuration: model={model}, temperature={temperature}")

        # Initialize database and embeddings
        logger.info("Setting up database manager")
        self.db_manager = DatabaseManager(database_url)

        logger.info(f"Setting up embedding manager with model: {embedding_model}")
        self.embedding_manager = EmbeddingManager(embedding_model)

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

        # Initialize tools - only Fed scraper for this agent
        logger.info("Setting up Fed analysis tools")
        self.tools = [
            FedWebScraperTool(
                db_manager=self.db_manager,
                embedding_manager=self.embedding_manager
            )
        ]
        logger.debug(f"Initialized {len(self.tools)} tools for Fed analysis")

        # Create agent
        logger.debug("Creating Fed analysis agent")
        self.agent = create_openai_tools_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=FED_ANALYSIS_AGENT_PROMPT
        )

        # Create executor
        logger.debug("Creating Fed analysis agent executor")
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=False,
            max_iterations=max_iterations,
            return_intermediate_steps=False
        )

        logger.info("FedAnalysisAgent initialization completed successfully")

    def analyze_fed_data(self,
                         fed_url: str,
                         target_content: str = "FOMC interest rates monetary policy") -> Dict[str, Any]:
        """
        Analyze Fed data and determine if screening is needed

        Returns:
            Dict containing:
            - success: bool
            - analysis_result: dict with market environment analysis
            - screening_needed: bool (for now always True)
            - execution_id: str
            - similar_analyses: list
            - llm_usage: dict
        """

        logger.info(f"Starting Fed data analysis for URL: {fed_url}")
        logger.info(f"Target content: {target_content}")

        # Start agent execution tracking
        execution_id = self.db_manager.start_agent_execution(
            user_prompt=f"Analyze Fed data from {fed_url} for {target_content}",
            execution_type="fed_analysis_only",
            metadata={'fed_url': fed_url, 'target_content': target_content}
        )

        logger.info(f"Started Fed analysis execution tracking with ID: {execution_id}")

        # Initialize LLM tracker for this execution
        llm_tracker = UniversalLLMUsageTracker(self.db_manager, execution_id)

        # Set execution ID for tools to use
        for tool in self.tools:
            if hasattr(tool, 'set_execution_id'):
                tool.set_execution_id(execution_id)

        # Check for similar past analyses
        logger.debug("Searching for similar past analyses")
        similar_analyses = self._find_similar_past_analyses(target_content)

        if similar_analyses:
            logger.info(f"Found {len(similar_analyses)} similar past analyses")
        else:
            logger.info("No similar past analyses found")

        # Create analysis prompt
        prompt = f"""
        Analyze the Federal Reserve economic data and assess the market environment.

        Task:
        1. Scrape Fed website: {fed_url}
        2. Target content: {target_content}
        3. Analyze the economic implications and market environment
        4. Determine the overall market sentiment and conditions

        {"Previous similar analyses found: " + json.dumps(similar_analyses, indent=2) if similar_analyses else ""}

        Focus your analysis on:
        - Interest rate direction and policy stance (hawkish/dovish/neutral)
        - Market sentiment indicators from Fed communications
        - Economic outlook and growth concerns
        - Inflation trends and Fed responses
        - Financial stability considerations
        - Sector rotation implications (growth vs value, rate-sensitive sectors)

        Provide a structured analysis with:
        1. Overall market environment classification
        2. Key economic factors identified
        3. Sector impact assessment
        4. Risk sentiment evaluation

        Do NOT execute any stock screeners - only analyze the Fed data.
        """

        try:
            logger.info("Executing Fed analysis agent")
            # Execute agent with tracking callback
            config = RunnableConfig(callbacks=[llm_tracker])
            result = self.agent_executor.invoke({"input": prompt}, config=config)

            logger.info("Fed analysis agent execution completed successfully")

            # Parse the analysis result from agent output
            analysis_result = self._parse_fed_analysis(result.get('output', ''))

            # Get LLM usage stats for this execution
            logger.debug("Retrieving LLM usage statistics")
            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)

            # For now, always return True for screening needed
            # TODO: Add intelligent decision logic here
            screening_needed = self._should_create_screener(analysis_result)

            # Complete the execution tracking
            logger.debug("Completing Fed analysis execution tracking")
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=result.get('output', ''),
                success=True
            )

            logger.info(f"Fed analysis completed successfully. Screening needed: {screening_needed}")
            logger.info(f"LLM cost: ${llm_stats['total_cost']:.4f}")

            return {
                'success': True,
                'execution_id': execution_id,
                'analysis_result': analysis_result,
                'screening_needed': screening_needed,
                'agent_output': result.get('output', ''),
                'intermediate_steps': result.get('intermediate_steps', []),
                'similar_past_analyses': similar_analyses,
                'llm_usage': llm_stats,
                'fed_url': fed_url,
                'target_content': target_content,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Fed analysis failed: {str(e)}", exc_info=True)

            # Get partial LLM usage stats even on error
            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)

            # Complete execution with error
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=f"Error during Fed analysis: {str(e)}",
                success=False,
                error_message=str(e)
            )

            logger.warning(f"LLM costs incurred despite error: ${llm_stats['total_cost']:.4f}")

            return {
                'success': False,
                'execution_id': execution_id,
                'error': str(e),
                'llm_usage': llm_stats,
                'fed_url': fed_url,
                'timestamp': datetime.now().isoformat()
            }

    def _parse_fed_analysis(self, agent_output: str) -> Dict[str, Any]:
        """Parse the Fed analysis output into structured data"""

        logger.debug("Parsing Fed analysis output")

        # Basic parsing - extract key information from agent output
        # This is a simplified parser - could be made more sophisticated
        analysis = {
            'market_environment': 'neutral',  # Default
            'policy_stance': 'neutral',
            'risk_sentiment': 'neutral',
            'sector_implications': {},
            'key_factors': [],
            'raw_analysis': agent_output
        }

        # Simple keyword-based parsing
        output_lower = agent_output.lower()

        # Policy stance detection
        if any(word in output_lower for word in ['hawkish', 'tightening', 'raising rates', 'aggressive']):
            analysis['policy_stance'] = 'hawkish'
        elif any(word in output_lower for word in ['dovish', 'accommodative', 'cutting rates', 'supportive']):
            analysis['policy_stance'] = 'dovish'

        # Market environment detection
        if any(word in output_lower for word in ['risk-off', 'defensive', 'cautious', 'uncertainty']):
            analysis['market_environment'] = 'risk_off'
        elif any(word in output_lower for word in ['risk-on', 'bullish', 'optimistic', 'growth']):
            analysis['market_environment'] = 'risk_on'

        # Risk sentiment
        if any(word in output_lower for word in ['high risk', 'volatile', 'uncertain', 'concerns']):
            analysis['risk_sentiment'] = 'high_risk'
        elif any(word in output_lower for word in ['low risk', 'stable', 'confident', 'positive']):
            analysis['risk_sentiment'] = 'low_risk'

        logger.debug(f"Parsed analysis: {analysis['market_environment']}, {analysis['policy_stance']}")
        return analysis

    def _should_create_screener(self, analysis_result: Dict[str, Any]) -> bool:
        """
        Determine if a screener should be created based on analysis

        For now, always returns True as requested.
        TODO: Add intelligent decision logic
        """

        logger.debug("Evaluating screening need decision")

        # For now, always return True as requested
        # Future logic could consider:
        # - Significance of Fed announcements
        # - Market volatility levels
        # - Recent screening activity
        # - Analysis confidence levels

        screening_needed = True
        logger.info(f"Screening decision: {screening_needed} (pass-through logic)")

        return screening_needed

    def _find_similar_past_analyses(self, target_content: str, limit: int = 3) -> list:
        """Find similar past analyses using embeddings"""
        logger.debug(f"Searching for similar analyses with target content: {target_content}")

        try:
            # Create embedding for target content
            query_embedding = self.embedding_manager.embed_query(target_content)

            if query_embedding:
                logger.debug("Query embedding created successfully")
                # Search for similar content
                similar_content = self.db_manager.search_similar_content(
                    query_embedding=query_embedding,
                    limit=limit,
                    source="fed_website"
                )

                logger.debug(f"Found {len(similar_content)} similar content items")
                return similar_content
            else:
                logger.warning("Failed to create query embedding")

        except Exception as e:
            logger.warning(f"Error finding similar analyses: {e}")

        return []

    def get_analysis_history(self, limit: int = 10) -> list:
        """Get recent Fed analysis history"""
        logger.debug(f"Retrieving Fed analysis history (limit: {limit})")

        try:
            with self.db_manager.get_session() as session:
                from database.models import AgentExecution

                executions = session.query(AgentExecution) \
                    .filter(AgentExecution.execution_type == "fed_analysis_only") \
                    .order_by(AgentExecution.started_at.desc()) \
                    .limit(limit).all()

                history = [
                    {
                        'id': str(exec.id),
                        'user_prompt': exec.user_prompt[:200] + '...' if len(
                            exec.user_prompt) > 200 else exec.user_prompt,
                        'success': exec.success,
                        'started_at': exec.started_at.isoformat(),
                        'completed_at': exec.completed_at.isoformat() if exec.completed_at else None
                    }
                    for exec in executions
                ]

                logger.debug(f"Retrieved {len(history)} Fed analysis records")
                return history

        except Exception as e:
            logger.error(f"Error getting Fed analysis history: {e}")
            return []