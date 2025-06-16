from langchain.tools import BaseTool
from typing import Type, Optional, Dict, Any
from tradingview_screener import Query, col, And
import json
from datetime import datetime
import logging
import time

from schema.tool_schemas import TradingViewQueryInput, ScreenerFilter

logger = logging.getLogger(__name__)


class TradingViewQueryTool(BaseTool):
    """Enhanced TradingView query tool with database persistence"""

    name: str = "tradingview_query"
    description: str = """
    Executes TradingView screener queries and saves inputs/results to database.
    Returns filtered stock data and database IDs for tracking.
    """
    args_schema: Type[TradingViewQueryInput] = TradingViewQueryInput

    # Use class variables to avoid Pydantic issues
    _db_manager = None
    _execution_id = None
    _cookies = None

    def __init__(self, db_manager=None, execution_id: Optional[str] = None,
                 cookies: Optional[Dict] = None):
        super().__init__()
        # Store in class variables
        TradingViewQueryTool._db_manager = db_manager
        TradingViewQueryTool._execution_id = execution_id
        TradingViewQueryTool._cookies = cookies

    def set_execution_id(self, execution_id: str):
        """Set the current agent execution ID"""
        TradingViewQueryTool._execution_id = execution_id

    def _run(self, columns: list, filters: list, sort_column: str,
             limit: int = 50, sort_ascending: bool = False,
             reasoning: Optional[str] = None) -> str:
        """Execute TradingView query and save to database"""
        start_time = time.time()

        try:
            # Save screener input to database
            input_id = None
            if self._db_manager and self._execution_id:
                # Convert filters to serializable format
                serializable_filters = []
                for f in filters:
                    if hasattr(f, 'model_dump'):  # Pydantic v2
                        serializable_filters.append(f.model_dump())
                    elif hasattr(f, 'dict'):  # Pydantic v1
                        serializable_filters.append(f.dict())
                    elif isinstance(f, dict):
                        serializable_filters.append(f)
                    else:
                        serializable_filters.append(str(f))

                input_id = self._db_manager.save_screener_input(
                    execution_id=self._execution_id,
                    columns=columns,
                    filters=serializable_filters,
                    sort_column=sort_column,
                    sort_ascending=sort_ascending,
                    limit=limit,
                    reasoning=reasoning
                )

            # Build and execute query
            query = Query()
            query = query.select(*columns)
            combined_filters = []

            # Apply mandatory filters first using the proper TradingView syntax
            try:
                mandatory_filters = [
                    {"type": "not_equal", "column": "exchange", "value": "OTC"},
                ]

                # If any filter references Perf.Y or it's in selected columns
                if any("Perf.Y" in str(f) for f in filters) or "Perf.Y" in columns:
                    mandatory_filters.append({"type": "less_than", "column": "Perf.Y", "value": 1000})

                # Convert to query filters
                for f in mandatory_filters:
                    if f["type"] == "not_equal":
                        combined_filters.append(col(f["column"]) != f["value"])
                    elif f["type"] == "greater_than":
                        combined_filters.append(col(f["column"]) > f["value"])
                    elif f["type"] == "less_than":
                        combined_filters.append(col(f["column"]) < f["value"])


            except Exception as e:
                logger.warning(f"Error applying mandatory filters: {e}")

            for f in filters:
                if isinstance(f, dict):
                    f = ScreenerFilter(**f)
                if f.type == 'range':
                    combined_filters.append(col(f.column).between(f.min_value, f.max_value))
                elif f.type == 'greater_than':
                    combined_filters.append(col(f.column) > f.value)
                elif f.type == 'less_than':
                    combined_filters.append(col(f.column) < f.value)
                elif f.type == 'equals':
                    combined_filters.append(col(f.column) == f.value)
                elif f.type == 'column_comparison':
                    combined_filters.append(col(f.left_column) >= col(f.right_column))
                else:
                    logger.warning(f"Unknown filter type: {f.type}")
            query = query.where2(And(*combined_filters))
            query = query.order_by(sort_column, ascending=sort_ascending)
            query = query.limit(limit)

            # Execute query
            total_count, df = query.get_scanner_data(cookies=self._cookies)
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            # Prepare result data
            result_data = df.to_dict('records') if not df.empty else []

            # Save screener result to database
            result_id = None
            if self._db_manager and input_id:
                result_id = self._db_manager.save_screener_result(
                    input_id=input_id,
                    total_results=total_count,
                    returned_results=len(df),
                    result_data=result_data,
                    execution_time_ms=execution_time,
                    success=True
                )

            # Return structured result
            result = {
                'screener_input_id': input_id,
                'screener_result_id': result_id,
                'query_executed_at': datetime.now().isoformat(),
                'total_results': total_count,
                'returned_results': len(df),
                'execution_time_ms': execution_time,
                'columns': columns,
                'filters_applied': filters,
                'mandatory_filters_applied': mandatory_filters,  # Show what base filters were added
                'data_preview': result_data[:10],  # First 10 for immediate analysis
                'full_data_count': len(result_data),
                'success': True
            }

            logger.info(
                f"TradingView query executed: {total_count} total results, {len(df)} returned, saved with IDs {input_id}/{result_id}")
            return json.dumps(result, indent=2, default=str)

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            # Save error to database if we have input_id
            if self._db_manager and input_id:
                self._db_manager.save_screener_result(
                    input_id=input_id,
                    total_results=0,
                    returned_results=0,
                    result_data=[],
                    execution_time_ms=execution_time,
                    success=False,
                    error_message=str(e)
                )

            error_result = {
                'screener_input_id': input_id,
                'error': str(e),
                'query_executed_at': datetime.now().isoformat(),
                'execution_time_ms': execution_time,
                'success': False
            }

            logger.error(f"TradingView query error: {str(e)}")
            return json.dumps(error_result, indent=2)

    def _apply_filter(self, query: Query, filter_obj: ScreenerFilter) -> Query:
        """Apply a single filter to the query"""
        if filter_obj.type == 'range':
            return query.where(
                col(filter_obj.column).between(filter_obj.min_value, filter_obj.max_value)
            )
        elif filter_obj.type == 'greater_than':
            return query.where(col(filter_obj.column) > filter_obj.value)
        elif filter_obj.type == 'less_than':
            return query.where(col(filter_obj.column) < filter_obj.value)
        elif filter_obj.type == 'equals':
            return query.where(col(filter_obj.column) == filter_obj.value)
        elif filter_obj.type == 'column_comparison':
            return query.where(col(filter_obj.left_column) >= col(filter_obj.right_column))
        else:
            logger.warning(f"Unknown filter type: {filter_obj.type}")
            return query