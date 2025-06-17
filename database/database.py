from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime, timedelta
import json

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

    def save_scraped_data(self, source: str, url: str, target_content: str,
                          raw_content: str, metadata: Optional[Dict] = None) -> str:
        """Save scraped data and return ID"""
        with self.get_session() as session:
            scraped_data = ScrapedData(
                source=source,
                url=url,
                target_content=target_content,
                raw_content=raw_content,
                extra_metadata=json.dumps(metadata or {})  # Convert to JSON string for SQLite
            )
            session.add(scraped_data)
            session.flush()  # Get the ID
            scraped_data_id = scraped_data.id
            logger.info(f"Saved scraped data with ID: {scraped_data_id}")
            return scraped_data_id

    def save_embeddings(self, scraped_data_id: str, embeddings: List[Dict[str, Any]]):
        """Save embeddings for scraped data"""
        with self.get_session() as session:
            for embedding_data in embeddings:
                embedding = DataEmbedding(
                    scraped_data_id=scraped_data_id,
                    embedding_model=embedding_data['model'],
                    embedding_vector=json.dumps(embedding_data['vector']),  # Convert to JSON string
                    chunk_index=embedding_data.get('chunk_index', 0),
                    chunk_text=embedding_data['text']
                )
                session.add(embedding)
            logger.info(f"Saved {len(embeddings)} embeddings for scraped data {scraped_data_id}")

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

    def get_recent_scraped_data(self, source: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Get recent scraped data"""
        with self.get_session() as session:
            query = session.query(ScrapedData)
            if source:
                query = query.filter_by(source=source)

            results = query.order_by(ScrapedData.created_at.desc()).limit(limit).all()
            return [
                {
                    'id': r.id,
                    'source': r.source,
                    'url': r.url,
                    'content_preview': r.raw_content[:200] + '...' if len(r.raw_content) > 200 else r.raw_content,
                    'created_at': r.created_at.isoformat()
                }
                for r in results
            ]

    def search_similar_content(self, query_embedding: List[float],
                               limit: int = 5, source: Optional[str] = None) -> List[Dict]:
        """Search for similar content using embeddings (simplified - would use vector DB in production)"""
        # This is a simplified version - in production, use a proper vector database like ChromaDB/Pinecone
        with self.get_session() as session:
            query_builder = session.query(DataEmbedding).join(ScrapedData)
            if source:
                query_builder = query_builder.filter(ScrapedData.source == source)

            embeddings = query_builder.all()

            # Simple cosine similarity (use proper vector search in production)
            import numpy as np

            similarities = []
            for emb in embeddings:
                try:
                    stored_vector = np.array(json.loads(emb.embedding_vector))  # Parse JSON string
                    query_vector = np.array(query_embedding)

                    # Cosine similarity
                    cosine_sim = np.dot(stored_vector, query_vector) / (
                            np.linalg.norm(stored_vector) * np.linalg.norm(query_vector)
                    )

                    similarities.append({
                        'embedding_id': emb.id,
                        'scraped_data_id': emb.scraped_data_id,
                        'similarity': float(cosine_sim),
                        'text': emb.chunk_text,
                        'source': emb.scraped_data.source
                    })
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Error parsing embedding vector: {e}")
                    continue

            # Sort by similarity and return top results
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:limit]


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


    def get_recent_market_data(self,
                               data_type: Optional[str] = None,
                               ticker: Optional[str] = None,
                               limit: int = 100) -> List[Dict]:
        """Get recent market data with optional filters"""
        with self.get_session() as session:
            query = session.query(MarketData)

            if data_type:
                query = query.filter_by(data_type=data_type)
            if ticker:
                query = query.filter_by(ticker=ticker.upper())

            market_data_points = query.order_by(
                MarketData.retrieved_at.desc()
            ).limit(limit).all()

            return [
                {
                    'id': md.id,
                    'ticker': md.ticker,
                    'price': md.price,
                    'change_percent': md.change_percent,
                    'volume': md.volume,
                    'data_type': md.data_type,
                    'data_source': md.data_source,
                    'scraped_data_id': md.scraped_data_id,
                    'provider_timestamp': md.provider_timestamp.isoformat() if md.provider_timestamp else None,
                    'retrieved_at': md.retrieved_at.isoformat()
                }
                for md in market_data_points
            ]
