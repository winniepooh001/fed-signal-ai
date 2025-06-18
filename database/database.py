from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime, timedelta
import json
import hashlib

from database.models import Base, ScrapedData, ScreenerInput, ScreenerResult, AgentExecution, DataEmbedding, LLMUsage, MarketData

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and operations"""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self):
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")

    @contextmanager
    def get_session(self):
        """Get database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def save_llm_usage(self, agent_execution_id: Optional[str], model_name: str,
                       prompt_tokens: int, completion_tokens: int, total_tokens: int,
                       call_type: str, request_data: Optional[Dict] = None,
                       response_data: Optional[Dict] = None, cost_estimate: Optional[float] = None) -> str:
        """Save LLM usage data"""
        with self.get_session() as session:
            llm_usage = LLMUsage(
                agent_execution_id=agent_execution_id,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                call_type=call_type,
                request_data=json.dumps(request_data or {}),
                response_data=json.dumps(response_data or {}),
                cost_estimate=cost_estimate
            )
            session.add(llm_usage)
            session.flush()
            usage_id = llm_usage.id
            logger.info(f"Saved LLM usage with ID: {usage_id}")
            return usage_id

    def get_llm_usage_stats(self, agent_execution_id: Optional[str] = None,
                            time_range_hours: Optional[int] = None) -> Dict[str, Any]:
        """Get LLM usage statistics"""
        with self.get_session() as session:
            query = session.query(LLMUsage)

            if agent_execution_id:
                query = query.filter_by(agent_execution_id=agent_execution_id)

            if time_range_hours:
                cutoff_time = datetime.now() - timedelta(hours=time_range_hours)
                query = query.filter(LLMUsage.created_at >= cutoff_time)

            usage_records = query.all()

            if not usage_records:
                return {
                    'total_calls': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'breakdown': {}
                }

            stats = {
                'total_calls': len(usage_records),
                'total_prompt_tokens': sum(r.prompt_tokens for r in usage_records),
                'total_completion_tokens': sum(r.completion_tokens for r in usage_records),
                'total_tokens': sum(r.total_tokens for r in usage_records),
                'total_cost': sum(r.cost_estimate or 0 for r in usage_records),
                'breakdown': {}
            }

            # Breakdown by model
            for record in usage_records:
                model = record.model_name
                if model not in stats['breakdown']:
                    stats['breakdown'][model] = {
                        'calls': 0,
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0,
                        'cost': 0.0
                    }

                stats['breakdown'][model]['calls'] += 1
                stats['breakdown'][model]['prompt_tokens'] += record.prompt_tokens
                stats['breakdown'][model]['completion_tokens'] += record.completion_tokens
                stats['breakdown'][model]['total_tokens'] += record.total_tokens
                stats['breakdown'][model]['cost'] += record.cost_estimate or 0

            return stats

    def start_agent_execution(self, user_prompt: str, execution_type: str,
                              scraped_data_id: Optional[str] = None,
                              metadata: Optional[Dict] = None) -> str:
        """Start a new agent execution session"""
        with self.get_session() as session:
            execution = AgentExecution(
                scraped_data_id=scraped_data_id,
                user_prompt=user_prompt,
                execution_type=execution_type,
                execution_metadata=json.dumps(metadata or {})  # Convert to JSON string
            )
            session.add(execution)
            session.flush()
            execution_id = execution.id
            logger.info(f"Started agent execution with ID: {execution_id}")
            return execution_id

    def complete_agent_execution(self, execution_id: str, agent_reasoning: str,
                                 success: bool = True, error_message: Optional[str] = None):
        """Complete an agent execution session"""
        with self.get_session() as session:
            execution = session.query(AgentExecution).filter_by(id=execution_id).first()
            if execution:
                execution.agent_reasoning = agent_reasoning
                execution.success = success
                execution.error_message = error_message
                execution.completed_at = datetime.utcnow()
                logger.info(f"Completed agent execution {execution_id}")

    def save_screener_input(self, execution_id: str, columns: List[str],
                            filters: List[Any], sort_column: str,
                            sort_ascending: bool = False, limit: int = 50,
                            reasoning: Optional[str] = None) -> str:
        """Save screener input parameters"""
        with self.get_session() as session:
            # Convert ScreenerFilter objects to dictionaries
            filters_dict = []
            for f in filters:
                if hasattr(f, 'model_dump'):  # Pydantic v2
                    filters_dict.append(f.model_dump())
                elif hasattr(f, 'dict'):  # Pydantic v1
                    filters_dict.append(f.dict())
                elif isinstance(f, dict):
                    filters_dict.append(f)
                else:
                    filters_dict.append(str(f))  # Fallback

            screener_input = ScreenerInput(
                agent_execution_id=execution_id,
                columns=json.dumps(columns),  # Convert to JSON string
                filters=json.dumps(filters_dict),  # Convert to JSON string
                sort_column=sort_column,
                sort_ascending=sort_ascending,
                limit=limit,
                query_reasoning=reasoning
            )
            session.add(screener_input)
            session.flush()
            input_id = screener_input.id
            logger.info(f"Saved screener input with ID: {input_id}")
            return input_id

    def save_screener_result(self, input_id: str, total_results: int,
                             returned_results: int, result_data: List[Dict],
                             execution_time_ms: Optional[float] = None,
                             success: bool = True, error_message: Optional[str] = None) -> str:
        """Save screener query results"""
        with self.get_session() as session:
            screener_result = ScreenerResult(
                screener_input_id=input_id,
                total_results=total_results,
                returned_results=returned_results,
                result_data=json.dumps(result_data),  # Convert to JSON string
                query_executed_at=datetime.utcnow(),
                execution_time_ms=execution_time_ms,
                success=success,
                error_message=error_message
            )
            session.add(screener_result)
            session.flush()
            result_id = screener_result.id
            logger.info(f"Saved screener result with ID: {result_id}")
            return result_id


    def save_market_data_point(self,
                               ticker: str,
                               price: float,
                               data_type: str,
                               data_source: str,
                               scraped_data_id: Optional[str] = None,
                               change_percent: Optional[float] = None,
                               volume: Optional[int] = None,
                               market_cap: Optional[float] = None,
                               provider_timestamp: Optional[datetime] = None) -> str:
        """Save individual market data point"""
        with self.get_session() as session:
            market_data = MarketData(
                scraped_data_id=scraped_data_id,
                data_type=data_type,
                ticker=ticker.upper(),
                price=price,
                change_percent=change_percent,
                volume=volume,
                market_cap=market_cap,
                data_source=data_source,
                provider_timestamp=provider_timestamp,
                retrieved_at=datetime.utcnow()
            )
            session.add(market_data)
            session.flush()
            market_data_id = market_data.id
            logger.debug(f"Saved market data point: {ticker} from {data_source}")
            return market_data_id


    def get_market_data_by_scraped_id(self, scraped_data_id: str) -> List[Dict]:
        """Get market data points linked to a scraped data record"""
        with self.get_session() as session:
            market_data_points = session.query(MarketData).filter_by(
                scraped_data_id=scraped_data_id
            ).all()

            return [
                {
                    'id': md.id,
                    'ticker': md.ticker,
                    'price': md.price,
                    'change_percent': md.change_percent,
                    'volume': md.volume,
                    'data_type': md.data_type,
                    'data_source': md.data_source,
                    'provider_timestamp': md.provider_timestamp.isoformat() if md.provider_timestamp else None,
                    'retrieved_at': md.retrieved_at.isoformat()
                }
                for md in market_data_points
            ]

    def save_market_data_batch(self,
                               market_data_points: List[Dict[str, Any]],
                               batch_timestamp: Optional[datetime] = None,
                               scraped_data_id: Optional[str] = None) -> List[str]:
        """
        Save market data as a batch with consistent timestamp

        Args:
            market_data_points: List of market data dictionaries
            batch_timestamp: Consistent timestamp for this batch (defaults to now)
            scraped_data_id: Optional link to scraped data

        Returns:
            List of market data IDs
        """

        if batch_timestamp is None:
            batch_timestamp = datetime.utcnow()

        market_data_ids = []

        with self.get_session() as session:
            for dp in market_data_points:
                market_data = MarketData(
                    scraped_data_id=scraped_data_id,
                    batch_timestamp=batch_timestamp,  # NEW: Consistent batch time
                    data_type=dp.get('data_type', 'unknown'),
                    ticker=dp.get('ticker', '').upper(),
                    price=dp.get('price', 0.0),
                    change_percent=dp.get('change_percent'),
                    volume=dp.get('volume'),
                    market_cap=dp.get('market_cap'),
                    data_source=dp.get('data_source', 'unknown'),
                    provider_timestamp=dp.get('provider_timestamp'),
                    retrieved_at=datetime.utcnow()
                )
                session.add(market_data)
                session.flush()
                market_data_ids.append(market_data.id)

        logger.info(f"Saved batch of {len(market_data_ids)} market data points with timestamp {batch_timestamp}")
        return market_data_ids

    def get_latest_market_data_batch(self,
                                     data_types: Optional[List[str]] = None,
                                     exclude_scraped_linked: bool = False) -> List[Dict]:
        """
        Get the most recent batch of market data by batch_timestamp

        Args:
            data_types: Optional filter by data types
            exclude_scraped_linked: If True, only get data NOT linked to scraped_data_id

        Returns:
            List of market data points from the latest batch
        """

        with self.get_session() as session:
            # Find the latest batch timestamp
            query = session.query(MarketData.batch_timestamp)

            if exclude_scraped_linked:
                query = query.filter(MarketData.scraped_data_id.is_(None))

            if data_types:
                query = query.filter(MarketData.data_type.in_(data_types))

            latest_batch = query.order_by(MarketData.batch_timestamp.desc()).first()

            if not latest_batch:
                return []

            latest_timestamp = latest_batch[0]

            # Get all data from that batch
            data_query = session.query(MarketData).filter(
                MarketData.batch_timestamp == latest_timestamp
            )

            if data_types:
                data_query = data_query.filter(MarketData.data_type.in_(data_types))

            if exclude_scraped_linked:
                data_query = data_query.filter(MarketData.scraped_data_id.is_(None))

            market_data_points = data_query.all()

            return [
                {
                    'id': md.id,
                    'ticker': md.ticker,
                    'price': md.price,
                    'change_percent': md.change_percent,
                    'volume': md.volume,
                    'market_cap': md.market_cap,
                    'data_type': md.data_type,
                    'data_source': md.data_source,
                    'batch_timestamp': md.batch_timestamp.isoformat(),
                    'provider_timestamp': md.provider_timestamp.isoformat() if md.provider_timestamp else None,
                    'retrieved_at': md.retrieved_at.isoformat()
                }
                for md in market_data_points
            ]

    def get_market_data_by_batch_timestamp(self, batch_timestamp: datetime) -> List[Dict]:
        """Get market data by specific batch timestamp"""

        with self.get_session() as session:
            market_data_points = session.query(MarketData).filter(
                MarketData.batch_timestamp == batch_timestamp
            ).all()

            return [
                {
                    'id': md.id,
                    'ticker': md.ticker,
                    'price': md.price,
                    'change_percent': md.change_percent,
                    'volume': md.volume,
                    'market_cap': md.market_cap,
                    'data_type': md.data_type,
                    'data_source': md.data_source,
                    'batch_timestamp': md.batch_timestamp.isoformat(),
                    'scraped_data_id': md.scraped_data_id,
                    'provider_timestamp': md.provider_timestamp.isoformat() if md.provider_timestamp else None,
                    'retrieved_at': md.retrieved_at.isoformat()
                }
                for md in market_data_points
            ]

    def save_fed_content_to_scraped_data(self,
                                         fed_items: List[Dict[str, Any]],
                                         execution_id: Optional[str] = None) -> List[str]:
        """
        Save Fed content to existing ScrapedData table after successful email

        Args:
            fed_items: List of Fed content items from JSON
            execution_id: Agent execution ID for reference

        Returns:
            List of scraped_data IDs
        """

        saved_ids = []

        with self.get_session() as session:
            for item in fed_items:
                # Prepare metadata with sentiment and execution info
                metadata = {
                    'sentiment': item.get('sentiment', 'NEUTRAL'),
                    'sentiment_score': item.get('sentiment_score'),
                    'summary': item.get('summary', ''),
                    'published_date': item.get('published_date'),
                    'execution_id': execution_id,
                    'processed_via_email': True,
                    'processed_at': datetime.utcnow().isoformat()
                }

                # Create ScrapedData entry
                scraped_data = ScrapedData(
                    external_id=item.get('url', '').split('/')[-1] if item.get('url') else None,  # Extract ID from URL
                    source='fed_processed',  # Different source to distinguish from raw scrapes
                    url=item.get('url', ''),
                    target_content='processed_fed_content',
                    raw_content=item.get('full_content', '')[:5000],  # Truncate if too long
                    processed_content=item.get('summary', ''),
                    extra_metadata=json.dumps(metadata),
                    content_hash=hashlib.md5((item.get('url', '') + item.get('title', '')).encode()).hexdigest()[:32],
                    scraped_at=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )

                session.add(scraped_data)
                session.flush()
                saved_ids.append(scraped_data.id)

        logger.info(f"Saved {len(saved_ids)} Fed content items to ScrapedData table")
        return saved_ids
