from langchain.tools import BaseTool
from typing import List, Optional, Dict

from tools import FedWebScraperTool, TradingViewQueryTool
from database import DatabaseManager, EmbeddingManager


class ScreenerToolkit:
    """Enhanced LangChain toolkit with database persistence"""

    def __init__(self,
                 tradingview_cookies: Optional[Dict] = None,
                 db_manager: Optional[DatabaseManager] = None,
                 embedding_manager: Optional[EmbeddingManager] = None,
                 request_timeout: int = 10):
        self.tradingview_cookies = tradingview_cookies
        self.db_manager = db_manager
        self.embedding_manager = embedding_manager
        self.request_timeout = request_timeout

    def get_tools(self) -> List[BaseTool]:
        """Return tools with database capabilities"""
        tools = []

        if self.db_manager and self.embedding_manager:
            # Enhanced tools with database persistence
            tools.extend([
                FedWebScraperTool(
                    db_manager=self.db_manager,
                    embedding_manager=self.embedding_manager,
                    request_timeout=self.request_timeout
                ),
                TradingViewQueryTool(
                    db_manager=self.db_manager,
                    cookies=self.tradingview_cookies
                )
            ])
        else:
            # Fallback to basic tools without database
            from tools.fed_scraper import FedWebScraperTool as BasicFedTool
            from tools.tradingview_query import TradingViewQueryTool as BasicTVTool

            tools.extend([
                BasicFedTool(request_timeout=self.request_timeout),
                BasicTVTool(cookies=self.tradingview_cookies)
            ])

        return tools