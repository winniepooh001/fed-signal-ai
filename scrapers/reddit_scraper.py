# scrapers/reddit_scraper.py
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
import re
import json
import time
from scrapers.base_scraper import BaseScraper, ScrapedContent
from utils.logging_config import get_logger

logger = get_logger()


class RedditWSBScraper(BaseScraper):
    """Reddit WallStreetBets scraper with change detection"""

    def __init__(self, db_manager):
        super().__init__(db_manager, "reddit_wsb")
        self.base_url = "https://www.reddit.com/r/wallstreetbets"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Python:TradingViewScreener:v1.0 (by /u/YourUsername)'
        })

        # Filter criteria for relevant posts
        self.min_upvotes = 100
        self.min_comments = 10
        self.relevant_flairs = [
            'DD', 'Discussion', 'News', 'Earnings Thread',
            'Technical Analysis', 'Fundamentals', 'Loss', 'Gain'
        ]

        # Keywords that indicate trading relevance
        self.trading_keywords = [
            'earnings', 'fed', 'powell', 'rate', 'inflation', 'gdp',
            'yolo', 'calls', 'puts', 'options', 'strike', 'expiry',
            'bull', 'bear', 'moon', 'rocket', 'diamond', 'hands',
            'squeeze', 'short', 'gamma', 'IV', 'volatility'
        ]

    def scrape_new_content(self) -> List[ScrapedContent]:
        """Scrape Reddit WSB for new trading-relevant posts"""
        all_content = []

        # Define cutoff time
        if self.last_check_time:
            cutoff_time = self.last_check_time - timedelta(minutes=30)  # 30 min buffer
        else:
            cutoff_time = datetime.now() - timedelta(hours=24)  # Last 24 hours for first run

        logger.info(f"Reddit WSB: Looking for posts since {cutoff_time}")

        # Get posts from different sorting methods
        sort_methods = ['hot', 'new', 'rising']

        for sort_method in sort_methods:
            try:
                logger.info(f"Reddit WSB: Scraping {sort_method} posts")
                posts = self._get_posts(sort_method, cutoff_time)
                all_content.extend(posts)
                logger.info(f"Reddit WSB: Found {len(posts)} relevant posts in {sort_method}")

                # Rate limiting
                time.sleep(1)

            except Exception as e:
                logger.error(f"Reddit WSB: Failed to scrape {sort_method}: {e}")

        # Remove duplicates based on post ID
        seen_ids = set()
        unique_content = []
        for content in all_content:
            if content.id not in seen_ids:
                unique_content.append(content)
                seen_ids.add(content.id)

        # Sort by relevance score (upvotes + comments)
        unique_content.sort(key=lambda x: x.metadata.get('relevance_score', 0), reverse=True)

        return unique_content

    def _get_posts(self, sort_method: str, cutoff_time: datetime) -> List[ScrapedContent]:
        """Get posts from Reddit using JSON API"""
        posts = []

        try:
            # Use Reddit's JSON API
            url = f"{self.base_url}/{sort_method}.json"
            params = {'limit': 100}  # Get more posts to filter

            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if 'data' not in data or 'children' not in data['data']:
                logger.warning(f"Reddit WSB: Unexpected API response structure")
                return posts

            for post_data in data['data']['children']:
                try:
                    post = post_data['data']
                    content = self._process_post(post, cutoff_time)
                    if content:
                        posts.append(content)
                except Exception as e:
                    logger.debug(f"Reddit WSB: Error processing post: {e}")

        except Exception as e:
            logger.error(f"Reddit WSB: Error getting {sort_method} posts: {e}")

        return posts

    def _process_post(self, post: Dict, cutoff_time: datetime) -> ScrapedContent:
        """Process a single Reddit post"""
        try:
            # Extract basic info
            post_id = post.get('id', '')
            title = post.get('title', '')
            selftext = post.get('selftext', '')
            author = post.get('author', '[deleted]')
            subreddit = post.get('subreddit', '')

            # Get timestamps
            created_utc = post.get('created_utc', 0)
            published_date = datetime.fromtimestamp(created_utc)

            # Check if post is too old
            if published_date < cutoff_time:
                return None

            # Get engagement metrics
            upvotes = post.get('ups', 0)
            downvotes = post.get('downs', 0)
            num_comments = post.get('num_comments', 0)
            score = post.get('score', 0)
            upvote_ratio = post.get('upvote_ratio', 0)

            # Get flair
            flair = post.get('link_flair_text', '') or ''

            # Check relevance filters
            if not self._is_post_relevant(title, selftext, flair, upvotes, num_comments):
                return None

            # Build full content
            full_content = self._build_post_content(post, title, selftext, author)

            # Calculate relevance score
            relevance_score = self._calculate_relevance_score(
                title, selftext, upvotes, num_comments, flair
            )

            # Build URL
            url = f"https://reddit.com{post.get('permalink', '')}"

            content = ScrapedContent(
                id=f"wsb_{post_id}",
                title=title[:200],  # Limit title length
                content=full_content,
                url=url,
                published_date=published_date,
                source="reddit_wsb",
                metadata={
                    'author': author,
                    'subreddit': subreddit,
                    'flair': flair,
                    'upvotes': upvotes,
                    'downvotes': downvotes,
                    'num_comments': num_comments,
                    'score': score,
                    'upvote_ratio': upvote_ratio,
                    'relevance_score': relevance_score,
                    'content_type': 'reddit_post',
                    'sort_method': 'unknown'
                },
                content_hash=self._content_hash(full_content)
            )

            return content

        except Exception as e:
            logger.debug(f"Reddit WSB: Error processing post {post.get('id', 'unknown')}: {e}")
            return None

    def _is_post_relevant(self, title: str, selftext: str, flair: str,
                          upvotes: int, num_comments: int) -> bool:
        """Check if a post is relevant for trading analysis"""

        # Basic engagement filter
        if upvotes < self.min_upvotes or num_comments < self.min_comments:
            return False

        # Flair filter (if we have relevant flairs)
        if self.relevant_flairs and flair:
            if not any(relevant_flair.lower() in flair.lower()
                       for relevant_flair in self.relevant_flairs):
                return False

        # Content relevance check
        full_text = f"{title} {selftext}".lower()

        # Check for trading keywords
        keyword_matches = sum(1 for keyword in self.trading_keywords
                              if keyword in full_text)

        if keyword_matches < 2:  # Need at least 2 trading keywords
            return False

        # Filter out obvious spam/irrelevant posts
        spam_indicators = [
            'subscribe', 'follow me', 'join my', 'discord', 'telegram',
            'crypto', 'bitcoin', 'ethereum', 'coin', 'nft'
        ]

        spam_count = sum(1 for spam in spam_indicators if spam in full_text)
        if spam_count > 2:
            return False

        # Check title quality (not just emoji spam)
        title_words = len([w for w in title.split() if w.isalpha() and len(w) > 2])
        if title_words < 3:  # Need some actual words
            return False

        return True

    def _calculate_relevance_score(self, title: str, selftext: str,
                                   upvotes: int, num_comments: int, flair: str) -> float:
        """Calculate relevance score for ranking posts"""
        score = 0

        # Base engagement score
        score += upvotes * 0.1
        score += num_comments * 0.5

        # Flair bonuses
        flair_bonuses = {
            'DD': 50,  # Due Diligence posts are highly valuable
            'Discussion': 20,
            'Technical Analysis': 30,
            'Fundamentals': 25,
            'News': 15,
            'Earnings Thread': 20
        }

        if flair:
            for bonus_flair, bonus in flair_bonuses.items():
                if bonus_flair.lower() in flair.lower():
                    score += bonus
                    break

        # Keyword relevance
        full_text = f"{title} {selftext}".lower()

        # High-value keywords
        high_value_keywords = ['fed', 'powell', 'earnings', 'rate', 'inflation']
        score += sum(10 for keyword in high_value_keywords if keyword in full_text)

        # Medium-value keywords
        medium_value_keywords = ['options', 'calls', 'puts', 'volatility', 'analysis']
        score += sum(5 for keyword in medium_value_keywords if keyword in full_text)

        # Title quality bonus
        if len(title.split()) > 5:  # Descriptive titles
            score += 5

        return score

    def _build_post_content(self, post: Dict, title: str, selftext: str, author: str) -> str:
        """Build structured content from Reddit post"""

        content_parts = [
            f"Title: {title}",
            f"Author: u/{author}",
            f"Subreddit: r/{post.get('subreddit', 'wallstreetbets')}",
        ]

        # Add flair if available
        flair = post.get('link_flair_text')
        if flair:
            content_parts.append(f"Flair: {flair}")

        # Add engagement metrics
        content_parts.append(f"Upvotes: {post.get('ups', 0)}")
        content_parts.append(f"Comments: {post.get('num_comments', 0)}")
        content_parts.append(f"Upvote Ratio: {post.get('upvote_ratio', 0):.2f}")

        # Add post content
        if selftext and selftext.strip():
            content_parts.append(f"\nContent:\n{selftext[:2000]}")  # Limit content length

        # Add URL for reference
        if post.get('permalink'):
            content_parts.append(f"\nReddit URL: https://reddit.com{post['permalink']}")

        # Add timestamp
        created_utc = post.get('created_utc', 0)
        if created_utc:
            created_time = datetime.fromtimestamp(created_utc)
            content_parts.append(f"Posted: {created_time.strftime('%Y-%m-%d %H:%M UTC')}")

        return "\n".join(content_parts)

    def get_trending_tickers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Extract trending stock tickers from recent posts"""
        try:
            # Get recent posts
            recent_posts = self._get_posts('hot', datetime.now() - timedelta(hours=6))

            ticker_mentions = {}
            ticker_pattern = r'\b[A-Z]{1,5}\b'  # Stock ticker pattern

            for post in recent_posts:
                # Extract tickers from title and content
                text = f"{post.title} {post.content}"

                # Find potential tickers
                potential_tickers = re.findall(ticker_pattern, text)

                for ticker in potential_tickers:
                    # Filter out common words that match ticker pattern
                    if ticker in ['THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER', 'WAS', 'ONE',
                                  'OUR', 'HAD', 'DID', 'GET', 'MAY', 'HIM', 'OLD', 'SEE', 'NOW', 'WAY', 'WHO', 'BOY',
                                  'ITS', 'LET', 'PUT', 'TOO', 'END', 'WHY', 'TRY', 'GOD', 'SIX', 'DOG', 'EAT', 'AGO',
                                  'SIT', 'FUN', 'BAD', 'YES', 'YET', 'ARM', 'FAR', 'OFF', 'BAG', 'BUY', 'LAW', 'SON',
                                  'CAR', 'ADD', 'JOB', 'LOT', 'BED', 'TOP', 'ART', 'PAY', 'AGE', 'RED', 'WIN', 'BIG',
                                  'BOX', 'HOW', 'MAN', 'NEW', 'DAY', 'USE', 'HIS', 'HAS', 'SAY', 'SHE']:
                        continue

                    if ticker not in ticker_mentions:
                        ticker_mentions[ticker] = {
                            'ticker': ticker,
                            'mentions': 0,
                            'total_upvotes': 0,
                            'posts': []
                        }

                    ticker_mentions[ticker]['mentions'] += 1
                    ticker_mentions[ticker]['total_upvotes'] += post.metadata.get('upvotes', 0)
                    ticker_mentions[ticker]['posts'].append({
                        'title': post.title[:100],
                        'upvotes': post.metadata.get('upvotes', 0),
                        'url': post.url
                    })

            # Sort by mentions and upvotes
            trending = sorted(
                ticker_mentions.values(),
                key=lambda x: x['mentions'] * x['total_upvotes'],
                reverse=True
            )

            return trending[:limit]

        except Exception as e:
            logger.error(f"Reddit WSB: Error getting trending tickers: {e}")
            return []