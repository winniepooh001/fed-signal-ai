from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from langchain.schema.runnable import RunnableConfig
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
import json

from toolkit import ScreenerToolkit
from database import DatabaseManager, EmbeddingManager
from agents.prompts import SCREENER_AGENT_PROMPT
from utils.llm_callback import LLMUsageTracker
from database.models import AgentExecution

logger = logging.getLogger(__name__)


class ScreenerUpdateAgent:
    """Enhanced agent with database persistence and embedding search"""


    def __init__(self,
                 database_url: str,
                 model: str = "gpt-4-turbo-preview",
                 tradingview_cookies: Optional[Dict] = None,
                 embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
                 temperature: float = 0.1,
                 max_iterations: int = 5):
        """Initialize agent with database and embedding capabilities"""

        # Initialize database and embeddings
        self.db_manager = DatabaseManager(database_url)
        self.embedding_manager = EmbeddingManager(embedding_model)

        # Create tables if they don't exist
        self.db_manager.create_tables()

        self.llm_tracker = None
        # Initialize LLM
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
        )

        # Initialize enhanced toolkit with database managers
        self.toolkit = ScreenerToolkit(
            tradingview_cookies=tradingview_cookies,
            db_manager=self.db_manager,
            embedding_manager=self.embedding_manager
        )
        self.tools = self.toolkit.get_tools()

        # Create agent
        self.agent = create_openai_tools_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=SCREENER_AGENT_PROMPT
        )

        # Create executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            max_iterations=max_iterations,
            return_intermediate_steps=True
        )

    def analyze_fed_data_and_update_screeners(self,
                                              fed_url: str,
                                              target_content: str = "interest rates monetary policy") -> Dict[str, Any]:
        """Analyze Fed data with full database persistence and LLM tracking"""

        # Start agent execution tracking
        execution_id = self.db_manager.start_agent_execution(
            user_prompt=f"Analyze Fed data from {fed_url} for {target_content}",
            execution_type="fed_analysis",
            metadata={'fed_url': fed_url, 'target_content': target_content}
        )

        # Initialize LLM tracker for this execution
        self.llm_tracker = LLMUsageTracker(self.db_manager, execution_id)

        # Set execution ID for tools to use
        for tool in self.tools:
            if hasattr(tool, 'set_execution_id'):
                tool.set_execution_id(execution_id)

        # Check for similar past analyses
        similar_analyses = self._find_similar_past_analyses(target_content)

        prompt = f"""
        Analyze the latest Federal Reserve economic data and create appropriate stock screeners.

        Task:
        1. Scrape Fed website: {fed_url}
        2. Target content: {target_content}
        3. Analyze the economic implications for the next 1 - 4 weeks (trading horizon)
        4. Create ONE TradingView screener with at most 3 filters based on your analysis

        {"Previous similar analyses found: " + json.dumps(similar_analyses, indent=2) if similar_analyses else ""}

        Focus on how the economic data affects:
        - Interest rate sensitive for the various sectors
        - Liquidity and risk appetite of average investor and opportunity
        - Growth vs Value rotation  
          Dovish signals favor tech, growth, discretionary sectors
          Hawkish signals favor banks (net interest margin), utilities, staples
        - Dollar and inflation guidance effects
        - Forward guidance & volatility triggers
        - Look for reaction plays historically correlated with Fed meetings
        
        For the screen query, succinct rationalization in one sentence
        """

        try:
            # Execute agent with tracking callback
            config = RunnableConfig(callbacks=[self.llm_tracker])
            result = self.agent_executor.invoke({"input": prompt}, config=config)

            # Get LLM usage stats for this execution
            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)

            # Complete the execution tracking
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=result.get('output', ''),
                success=True
            )

            return {
                'success': True,
                'execution_id': execution_id,
                'agent_output': result.get('output', ''),
                'intermediate_steps': result.get('intermediate_steps', []),
                'similar_past_analyses': similar_analyses,
                'llm_usage': llm_stats,  # Include LLM usage stats
                'fed_url': fed_url,
                'target_content': target_content,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            # Get partial LLM usage stats even on error
            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)

            # Complete execution with error
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=f"Error during execution: {str(e)}",
                success=False,
                error_message=str(e)
            )

            logger.error(f"Agent execution error: {str(e)}")
            return {
                'success': False,
                'execution_id': execution_id,
                'error': str(e),
                'llm_usage': llm_stats,  # Include LLM usage stats even on error
                'fed_url': fed_url,
                'timestamp': datetime.now().isoformat()
            }

    def get_usage_statistics(self, time_range_hours: Optional[int] = 24) -> Dict[str, Any]:
        """Get LLM usage statistics for the specified time range"""
        return self.db_manager.get_llm_usage_stats(time_range_hours=time_range_hours)

    def create_custom_screeners(self, user_prompt: str) -> Dict[str, Any]:
        """Create screeners based on custom user analysis prompt - LLM decides what's best"""

        execution_id = self.db_manager.start_agent_execution(
            user_prompt=user_prompt,
            execution_type="custom_analysis"
        )

        # Set execution ID for tools
        for tool in self.tools:
            if hasattr(tool, 'set_execution_id'):
                tool.set_execution_id(execution_id)

        try:
            # Execute with LLM tracking
            llm_tracker = LLMUsageTracker(self.db_manager, execution_id)

            # Add callback temporarily
            original_callbacks = self.agent_executor.callbacks or []
            self.agent_executor.callbacks = original_callbacks + [llm_tracker]

            result = self.agent_executor.invoke({"input": user_prompt})

            # Restore callbacks
            self.agent_executor.callbacks = original_callbacks

            # Get usage stats
            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)

            # Complete execution
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=result.get('output', ''),
                success=True
            )

            return {
                'success': True,
                'execution_id': execution_id,
                'agent_output': result.get('output', ''),
                'intermediate_steps': result.get('intermediate_steps', []),
                'llm_usage': llm_stats,
                'user_prompt': user_prompt,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            # Restore callbacks on error
            self.agent_executor.callbacks = original_callbacks

            llm_stats = self.db_manager.get_llm_usage_stats(agent_execution_id=execution_id)
            self.db_manager.complete_agent_execution(
                execution_id=execution_id,
                agent_reasoning=f"Error: {str(e)}",
                success=False,
                error_message=str(e)
            )

            return {
                'success': False,
                'execution_id': execution_id,
                'error': str(e),
                'llm_usage': llm_stats,
                'user_prompt': user_prompt,
                'timestamp': datetime.now().isoformat()
            }
    def _find_similar_past_analyses(self, target_content: str, limit: int = 3) -> List[Dict]:
        """Find similar past analyses using embeddings"""
        try:
            # Create embedding for target content
            query_embedding = self.embedding_manager.embed_query(target_content)

            if query_embedding:
                # Search for similar content
                similar_content = self.db_manager.search_similar_content(
                    query_embedding=query_embedding,
                    limit=limit,
                    source="fed_website"
                )

                return similar_content

        except Exception as e:
            logger.warning(f"Error finding similar analyses: {e}")

        return []

    def get_execution_history(self, limit: int = 10) -> List[Dict]:
        """Get recent execution history"""
        try:
            with self.db_manager.get_session() as session:


                executions = session.query(AgentExecution) \
                    .order_by(AgentExecution.started_at.desc()) \
                    .limit(limit).all()

                return [
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
        except Exception as e:
            logger.error(f"Error getting execution history: {e}")
            return []

    def get_screener_results_by_execution(self, execution_id: str) -> List[Dict]:
        """Get all screener results for a specific execution"""
        try:
            with self.db_manager.get_session() as session:
                from database.models import ScreenerResult, ScreenerInput

                results = session.query(ScreenerResult) \
                    .join(ScreenerInput) \
                    .filter(ScreenerInput.agent_execution_id == execution_id) \
                    .all()

                return [
                    {
                        'result_id': str(result.id),
                        'input_id': str(result.screener_input_id),
                        'total_results': result.total_results,
                        'returned_results': result.returned_results,
                        'success': result.success,
                        'executed_at': result.query_executed_at.isoformat(),
                        'execution_time_ms': result.execution_time_ms,
                        'data_preview': result.result_data[:5] if result.result_data else []
                    }
                    for result in results
                ]
        except Exception as e:
            logger.error(f"Error getting screener results: {e}")
            return []
