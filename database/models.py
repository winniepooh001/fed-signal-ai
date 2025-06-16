from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.sqlite import TEXT
from datetime import datetime
import uuid

Base = declarative_base()


class ScrapedData(Base):
    """Store scraped data from various sources"""
    __tablename__ = "scraped_data"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(100), nullable=False)  # 'fed_website', 'twitter', etc.
    url = Column(TEXT, nullable=True)
    target_content = Column(String(500), nullable=True)
    raw_content = Column(TEXT, nullable=False)
    processed_content = Column(TEXT, nullable=True)
    extra_metadata = Column(TEXT, nullable=True)  # Changed from 'metadata' to 'extra_metadata'
    scraped_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    embeddings = relationship("DataEmbedding", back_populates="scraped_data")
    agent_executions = relationship("AgentExecution", back_populates="scraped_data")


class DataEmbedding(Base):
    """Store embeddings for scraped content"""
    __tablename__ = "data_embeddings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scraped_data_id = Column(String, ForeignKey("scraped_data.id"), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    embedding_vector = Column(TEXT, nullable=False)  # JSON as text for SQLite
    chunk_index = Column(Integer, default=0)
    chunk_text = Column(TEXT, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    scraped_data = relationship("ScrapedData", back_populates="embeddings")


class AgentExecution(Base):
    """Store complete agent execution sessions"""
    __tablename__ = "agent_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scraped_data_id = Column(String, ForeignKey("scraped_data.id"), nullable=True)
    user_prompt = Column(TEXT, nullable=False)
    agent_reasoning = Column(TEXT, nullable=True)
    execution_type = Column(String(50), nullable=False)
    success = Column(Boolean, default=True)
    error_message = Column(TEXT, nullable=True)
    execution_metadata = Column(TEXT, nullable=True)  # JSON as text
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    scraped_data = relationship("ScrapedData", back_populates="agent_executions")
    screener_inputs = relationship("ScreenerInput", back_populates="agent_execution")
    llm_usage = relationship("LLMUsage", back_populates="agent_execution")  # Add this


class ScreenerInput(Base):
    """Store screener input parameters"""
    __tablename__ = "screener_inputs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_execution_id = Column(String, ForeignKey("agent_executions.id"), nullable=False)
    columns = Column(TEXT, nullable=False)  # JSON as text
    filters = Column(TEXT, nullable=False)  # JSON as text
    sort_column = Column(String(100), nullable=False)
    sort_ascending = Column(Boolean, default=False)
    limit = Column(Integer, default=50)
    query_reasoning = Column(TEXT, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    agent_execution = relationship("AgentExecution", back_populates="screener_inputs")
    screener_results = relationship("ScreenerResult", back_populates="screener_input")


class ScreenerResult(Base):
    """Store screener query results"""
    __tablename__ = "screener_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    screener_input_id = Column(String, ForeignKey("screener_inputs.id"), nullable=False)
    total_results = Column(Integer, nullable=False)
    returned_results = Column(Integer, nullable=False)
    result_data = Column(TEXT, nullable=False)  # JSON as text
    query_executed_at = Column(DateTime, nullable=False)
    execution_time_ms = Column(Float, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(TEXT, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    screener_input = relationship("ScreenerInput", back_populates="screener_results")


class LLMUsage(Base):
    """Track LLM API calls and token usage"""
    __tablename__ = "llm_usage"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_execution_id = Column(String, ForeignKey("agent_executions.id"), nullable=True)
    model_name = Column(String(100), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    call_type = Column(String(50), nullable=False)  # 'agent_execution', 'tool_call', etc.
    request_data = Column(TEXT, nullable=True)  # JSON of request
    response_data = Column(TEXT, nullable=True)  # JSON of response
    cost_estimate = Column(Float, nullable=True)  # Estimated cost in USD
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    agent_execution = relationship("AgentExecution", back_populates="llm_usage")