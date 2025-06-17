
import sys

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))



@dataclass
class SentimentResult:
    """Sentiment analysis result"""
    score: float  # -1 to 1
    confidence: float  # 0 to 1
    model_name: str
    relevant: bool = False


@dataclass
class FedContent:
    """Fed content item"""
    url: str
    title: str
    content: str
    published_date: datetime
    content_hash: str
    file_type: str
    sentiment: Optional[SentimentResult] = None
    summary: Optional[str] = None  # Add this field