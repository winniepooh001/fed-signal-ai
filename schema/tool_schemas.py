from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional

class ScreenerFilter(BaseModel):
    """Schema for screener filter configuration"""
    type: str = Field(description="Filter type: range, greater_than, less_than, equals, column_comparison")
    column: Optional[str] = Field(None, description="Column to filter on")
    value: Optional[Any] = Field(None, description="Value to compare against")
    min_value: Optional[float] = Field(None, description="Minimum value for range filter")
    max_value: Optional[float] = Field(None, description="Maximum value for range filter")
    left_column: Optional[str] = Field(None, description="Left column for column comparison")
    right_column: Optional[str] = Field(None, description="Right column for column comparison")

class FedWebScraperInput(BaseModel):
    """Input schema for Fed website scraper"""
    url: str = Field(description="Fed website URL to scrape")
    target_content: str = Field(
        default="interest rates economic outlook",
        description="Specific content to look for"
    )

class TradingViewQueryInput(BaseModel):
    """Input schema for TradingView screener query"""
    columns: List[str] = Field(description="Columns to select for the screener")
    filters: List[ScreenerFilter] = Field(description="Filters to apply to the screener")
    sort_column: str = Field(description="Column to sort by")
    limit: int = Field(default=50, description="Number of results to return")
    sort_ascending: bool = Field(default=False, description="Sort order")