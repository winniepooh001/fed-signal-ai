from pydantic import BaseModel, Field, validator
from typing import Dict, List, Any, Optional, Union


class ScreenerFilter(BaseModel):
    """Schema for screener filter configuration"""
    type: str = Field(description="Filter type: range, greater_than, less_than, equals, in, column_comparison")
    column: Optional[str] = Field(None, description="Column to filter on")
    value: Optional[Any] = Field(None, description="Single value for equals/greater_than/less_than filters")
    values: Optional[List[Any]] = Field(None, description="List of values for 'in' filter type")
    min_value: Optional[float] = Field(None, description="Minimum value for range filter")
    max_value: Optional[float] = Field(None, description="Maximum value for range filter")
    left_column: Optional[str] = Field(None, description="Left column for column comparison")
    right_column: Optional[str] = Field(None, description="Right column for column comparison")

    @validator('type')
    def validate_filter_type(cls, v):
        valid_types = ['range', 'greater_than', 'less_than', 'equals', 'in', 'column_comparison']
        if v not in valid_types:
            raise ValueError(f"Filter type must be one of: {valid_types}")
        return v

    @validator('values')
    def validate_values_for_in_filter(cls, v, values):
        if values.get('type') == 'in' and (not v or len(v) == 0):
            raise ValueError("'in' filter type requires non-empty 'values' list")
        return v

    @validator('min_value')
    def validate_range_min(cls, v, values):
        if values.get('type') == 'range' and v is None:
            raise ValueError("'range' filter type requires 'min_value'")
        return v

    @validator('max_value')
    def validate_range_max(cls, v, values):
        if values.get('type') == 'range' and v is None:
            raise ValueError("'range' filter type requires 'max_value'")
        return v


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

    @validator('filters')
    def validate_no_duplicate_columns(cls, v):
        """Prevent multiple filters on the same column (except ranges)"""
        column_counts = {}
        for filter_obj in v:
            if filter_obj.column:
                column_counts[filter_obj.column] = column_counts.get(filter_obj.column, 0) + 1

        # Check for problematic duplicates
        for column, count in column_counts.items():
            if count > 1:
                # Allow multiple filters only if they're range components or explicitly allowed
                column_filters = [f for f in v if f.column == column]
                filter_types = [f.type for f in column_filters]

                # Allow range + greater_than/less_than combinations, but not multiple equals
                if 'equals' in filter_types and count > 1:
                    raise ValueError(f"Multiple 'equals' filters for column '{column}'. Use 'in' filter instead.")

                # Warn about other potential issues
                if set(filter_types) == {'greater_than', 'less_than'}:
                    # This is actually OK - represents a range
                    continue
                elif 'in' in filter_types and count > 1:
                    raise ValueError(f"Cannot combine 'in' filter with other filters on column '{column}'")

        return v


class EmailAgentInput(BaseModel):
    """Input schema for Email Agent"""
    recipient_emails: List[str] = Field(description="List of recipient email addresses")
    screener_result_id: str = Field(description="ID of the screener result to send")
    subject_prefix: str = Field(default="TradingView Screener Results", description="Email subject prefix")
    include_csv: bool = Field(default=True, description="Include CSV attachment")
    custom_message: Optional[str] = Field(None, description="Custom message to include in email")