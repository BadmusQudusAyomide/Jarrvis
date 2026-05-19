"""Twitter/X integration tools using Twitter API v2."""
import os
import logging
from pathlib import Path
from urllib.parse import unquote
from app.tools.base import BaseTool, ToolSchema, ToolParameter
from dotenv import load_dotenv

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Ensure env vars are available even when this module is used standalone.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def get_twitter_client():
    """Get authenticated Twitter API client."""
    if not TWEEPY_AVAILABLE:
        return None, "Error: tweepy not installed. Run: pip install tweepy"
    
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")
    if bearer_token:
        bearer_token = unquote(bearer_token)
    
    if not all([api_key, api_secret, access_token, access_secret]):
        return None, "Error: Twitter credentials not configured. Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET in .env"
    
    try:
        client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
        return client, None
    except Exception as e:
        return None, f"Error initializing Twitter client: {str(e)}"


class PostTweetTool(BaseTool):
    """Tool to post a tweet to Twitter/X."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="post_tweet",
            description="Post a tweet to Twitter/X. Can also reply to existing tweets. Maximum 280 characters.",
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="The tweet text content (max 280 characters)",
                    required=True
                ),
                ToolParameter(
                    name="reply_to",
                    type="string",
                    description="Tweet ID to reply to (optional)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, text: str, reply_to: str = None, **kwargs) -> str:
        if not text:
            return "Error: Tweet text cannot be empty"
        
        if len(text) > 280:
            return f"Error: Tweet is {len(text)} characters, exceeds 280 character limit"
        
        client, error = get_twitter_client()
        if error:
            return error
        
        try:
            reply_params = {}
            if reply_to:
                reply_params["in_reply_to_tweet_id"] = reply_to
            
            response = client.create_tweet(text=text, user_auth=True, **reply_params)
            tweet_id = response.data["id"]
            
            if reply_to:
                return f"Reply posted successfully! Tweet ID: {tweet_id}"
            return f"Tweet posted successfully! Tweet ID: {tweet_id}"
        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            return f"Error posting tweet: {str(e)}"


class GetHomeTimelineTool(BaseTool):
    """Tool to get the user's home timeline."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_home_timeline",
            description="Get the latest tweets from the user's home timeline (people they follow).",
            parameters=[
                ToolParameter(
                    name="count",
                    type="integer",
                    description="Number of tweets to retrieve (1-20, default 10)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, count: int = 10, **kwargs) -> str:
        client, error = get_twitter_client()
        if error:
            return error
        
        count = max(1, min(20, int(count)))
        
        try:
            tweets = client.get_home_timeline(
                max_results=count,
                tweet_fields=["created_at", "author_id"],
                user_auth=True
            )
            
            if not tweets.data:
                return "No tweets found in your timeline."
            
            formatted = []
            for tweet in tweets.data:
                created_at = tweet.created_at.strftime("%Y-%m-%d %H:%M") if tweet.created_at else "Unknown"
                formatted.append(
                    f"[@User {tweet.author_id}] [{created_at}]\n"
                    f"ID: {tweet.id}\n"
                    f"{tweet.text}\n"
                    f"---"
                )
            
            return f"Home Timeline ({len(tweets.data)} tweets):\n\n" + "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Failed to get timeline: {e}")
            return f"Error retrieving timeline: {str(e)}"


class SearchTweetsTool(BaseTool):
    """Tool to search for tweets."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="search_tweets",
            description="Search for tweets on Twitter/X by keyword, hashtag, or query.",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query (can include hashtags, keywords, from:username, etc.)",
                    required=True
                ),
                ToolParameter(
                    name="count",
                    type="integer",
                    description="Number of results (1-20, default 10)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, query: str, count: int = 10, **kwargs) -> str:
        if not query:
            return "Error: Search query cannot be empty"
        
        client, error = get_twitter_client()
        if error:
            return error
        
        count = max(1, min(20, int(count)))
        
        try:
            tweets = client.search_recent_tweets(
                query=query,
                max_results=count,
                tweet_fields=["created_at", "author_id", "public_metrics"]
            )
            
            if not tweets.data:
                return f"No tweets found for query: '{query}'"
            
            formatted = []
            for tweet in tweets.data:
                created_at = tweet.created_at.strftime("%Y-%m-%d %H:%M") if tweet.created_at else "Unknown"
                metrics = tweet.public_metrics
                likes = metrics.get("like_count", 0) if metrics else 0
                retweets = metrics.get("retweet_count", 0) if metrics else 0
                
                formatted.append(
                    f"[@User {tweet.author_id}] [{created_at}]\n"
                    f"ID: {tweet.id}\n"
                    f"{tweet.text}\n"
                    f"Likes: {likes} | Retweets: {retweets}\n"
                    f"---"
                )
            
            return f"Search results for '{query}' ({len(tweets.data)} tweets):\n\n" + "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Failed to search tweets: {e}")
            return f"Error searching tweets: {str(e)}"


class GetUserTweetsTool(BaseTool):
    """Tool to get tweets from a specific user."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_user_tweets",
            description="Get recent tweets from a specific Twitter/X user by their username.",
            parameters=[
                ToolParameter(
                    name="username",
                    type="string",
                    description="Twitter username (without @, e.g., 'elonmusk')",
                    required=True
                ),
                ToolParameter(
                    name="count",
                    type="integer",
                    description="Number of tweets (1-20, default 10)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, username: str, count: int = 10, **kwargs) -> str:
        if not username:
            return "Error: Username cannot be empty"
        
        username = username.lstrip("@")
        
        client, error = get_twitter_client()
        if error:
            return error
        
        count = max(1, min(20, int(count)))
        
        try:
            # Get user ID from username
            user = client.get_user(username=username, user_auth=True)
            if not user.data:
                return f"User @{username} not found"
            
            user_id = user.data.id
            
            tweets = client.get_users_tweets(
                id=user_id,
                max_results=count,
                tweet_fields=["created_at", "public_metrics"]
            )
            
            if not tweets.data:
                return f"No recent tweets from @{username}"
            
            formatted = []
            for tweet in tweets.data:
                created_at = tweet.created_at.strftime("%Y-%m-%d %H:%M") if tweet.created_at else "Unknown"
                metrics = tweet.public_metrics
                likes = metrics.get("like_count", 0) if metrics else 0
                
                formatted.append(
                    f"[{created_at}] ID: {tweet.id}\n"
                    f"{tweet.text}\n"
                    f"Likes: {likes}\n"
                    f"---"
                )
            
            return f"@{username}'s recent tweets ({len(tweets.data)}):\n\n" + "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Failed to get user tweets: {e}")
            return f"Error retrieving @{username}'s tweets: {str(e)}"


class DeleteTweetTool(BaseTool):
    """Tool to delete a tweet."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="delete_tweet",
            description="Delete a tweet by its ID (only works for tweets you own).",
            parameters=[
                ToolParameter(
                    name="tweet_id",
                    type="string",
                    description="The ID of the tweet to delete",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, tweet_id: str, **kwargs) -> str:
        if not tweet_id:
            return "Error: Tweet ID cannot be empty"
        
        client, error = get_twitter_client()
        if error:
            return error
        
        try:
            client.delete_tweet(id=tweet_id, user_auth=True)
            return f"Tweet {tweet_id} deleted successfully."
        except Exception as e:
            logger.error(f"Failed to delete tweet: {e}")
            return f"Error deleting tweet: {str(e)}"
