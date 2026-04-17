"""
Slack message logger - Captures Slack messages and saves them to a text file.
Supports filtering channels by inclusion or exclusion.
"""
import os
import argparse
import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Slack client with user token (xoxp)
# Using a user token (xoxp) instead of bot token (xoxb) allows the script to access
# all channels the user is a member of without needing the bot app to be invited to each channel.
SLACK_USER_TOKEN = os.environ.get("SLACK_USER_TOKEN")
if not SLACK_USER_TOKEN:
    raise ValueError("SLACK_USER_TOKEN environment variable not set. Use a user token (xoxp) instead of a bot token (xoxb).")

client = WebClient(token=SLACK_USER_TOKEN)
OUTPUT_FILE = "slack_messages.txt"
RATE_LIMIT_DELAY = 2  # 2 second delay between API calls (increased for safety)
CHANNEL_DELAY = 1.5  # Delay after processing each channel
USER_CACHE = {}  # Cache user names to avoid repeated API calls


def handle_rate_limit(retry_after=None):
    """Handle Slack API rate limiting with exponential backoff."""
    delay = int(retry_after) if retry_after else RATE_LIMIT_DELAY
    print(f"⏳ Rate limited by Slack. Waiting {delay} second(s)...")
    time.sleep(delay)


def api_call_with_retry(api_func, *args, max_retries=3, **kwargs):
    """Wrapper for API calls with retry logic and rate limit handling."""
    for attempt in range(max_retries):
        try:
            result = api_func(*args, **kwargs)
            # Success - add normal delay before next call
            time.sleep(RATE_LIMIT_DELAY)
            return result
        except SlackApiError as e:
            if e.response.get('error') == 'ratelimited':
                retry_after = e.response.get('headers', {}).get('Retry-After')
                handle_rate_limit(retry_after)
                if attempt < max_retries - 1:
                    continue
            raise
    return None


def filter_channels(channels, include_list=None, exclude_list=None):
    """
    Filter channels based on include/exclude lists.
    
    Args:
        channels: List of channel dicts
        include_list: List of channel names to include (if set, only these are included)
        exclude_list: List of channel names to exclude
    
    Returns:
        Filtered list of channels
    """
    filtered = channels
    
    # If include list is specified, only include those channels
    if include_list:
        include_set = {name.lower() for name in include_list}
        filtered = [c for c in filtered if c["name"].lower() in include_set]
        print(f"Including channels: {include_list}")
    
    # Exclude specified channels
    if exclude_list:
        exclude_set = {name.lower() for name in exclude_list}
        filtered = [c for c in filtered if c["name"].lower() not in exclude_set]
        print(f"Excluding channels: {exclude_list}")
    
    return filtered


def get_all_channels():
    """Fetch all channels the bot/user has access to and is a member of."""
    try:
        channels = []
        result = api_call_with_retry(client.conversations_list, limit=100, exclude_archived=True)
        # Only include channels where user is a member
        channels.extend([c for c in result["channels"] if c.get("is_member")])
        
        while result.get("response_metadata", {}).get("next_cursor"):
            result = api_call_with_retry(
                client.conversations_list,
                limit=100,
                exclude_archived=True,
                cursor=result["response_metadata"]["next_cursor"]
            )
            channels.extend([c for c in result["channels"] if c.get("is_member")])
        
        return channels
    except SlackApiError as e:
        print(f"Error fetching channels: {e}")
        return []


def get_messages_from_channel(channel_id, limit=1000, oldest=0):
    """Fetch messages from a specific channel.
    
    Args:
        channel_id: The channel ID to fetch from
        limit: Maximum number of messages to fetch
        oldest: Unix timestamp - only fetch messages on or after this time
    """
    try:
        messages = []
        result = api_call_with_retry(client.conversations_history, channel=channel_id, limit=100, oldest=oldest)
        messages.extend(result["messages"])
        
        # Pagination: get older messages
        while result.get("has_more") and len(messages) < limit:
            result = api_call_with_retry(
                client.conversations_history,
                channel=channel_id,
                limit=100,
                oldest=oldest,
                cursor=result.get("response_metadata", {}).get("next_cursor")
            )
            messages.extend(result["messages"])
        
        return messages[:limit]
    except SlackApiError as e:
        print(f"Error fetching messages from {channel_id}: {e}")
        return []


def get_user_name(user_id):
    """Fetch user name by user ID with caching."""
    # Check cache first
    if user_id in USER_CACHE:
        return USER_CACHE[user_id]
    
    try:
        result = api_call_with_retry(client.users_info, user=user_id)
        user_name = result["user"]["real_name"] or result["user"]["name"]
        USER_CACHE[user_id] = user_name  # Cache it
        return user_name
    except SlackApiError:
        return user_id


def format_message(message, channel_name, user_name):
    """Format a message for writing to file."""
    text = message.get("text", "")
    return f"{text}\n"


def log_all_messages(include_channels=None, exclude_channels=None):
    """Log all messages from all channels to a file.
    
    Args:
        include_channels: List of channel names to include (only these will be logged)
        exclude_channels: List of channel names to exclude
    """
    print("Starting Slack message logging...")
    print("Mode: Scraping old messages only (not listening for new ones)")
    print(f"Rate limit protection: {RATE_LIMIT_DELAY}s delay between API calls")
    
    # Calculate timestamp for 1 year and 5 months ago (approximately 17 months)
    oldest_date = datetime.now() - timedelta(days=365 + 150)  # 515 days
    oldest = oldest_date.timestamp()
    cutoff_str = oldest_date.strftime("%Y-%m-%d")
    print(f"Fetching messages from {cutoff_str} onward (1 year and 5 months back).\n")
    
    channels = get_all_channels()
    print(f"Found {len(channels)} channels available")
    
    # Apply channel filtering
    channels = filter_channels(channels, include_channels, exclude_channels)
    print(f"Processing {len(channels)} channels after filtering")
    print(f"Estimated time: ~{len(channels) * (CHANNEL_DELAY + 2)} seconds\n")
    
    if not channels:
        print("No channels to process after filtering!")
        return
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for idx, channel in enumerate(channels, 1):
            channel_id = channel["id"]
            channel_name = channel["name"]
            
            print(f"[{idx}/{len(channels)}] Processing #{channel_name}...", end="", flush=True)
            
            messages = get_messages_from_channel(channel_id, oldest=oldest)
            if messages:
                print(f" {len(messages)} messages found")
                
                for message in reversed(messages):  # Reverse to get chronological order
                    if "user" in message:
                        user_id = message["user"]
                        user_name = get_user_name(user_id)
                        formatted = format_message(message, channel_name, user_name)
                        f.write(formatted)
                    elif "bot_id" in message:
                        # Handle bot messages if needed
                        bot_name = message.get("username", "bot")
                        formatted = format_message(message, channel_name, bot_name)
                        f.write(formatted)
            else:
                print(" (no messages)")
            
            # Delay between channels to avoid rate limiting
            if idx < len(channels):
                time.sleep(CHANNEL_DELAY)
    
    print(f"\nLogging complete! Messages saved to {OUTPUT_FILE}")


def stream_new_messages():
    """Stream and log new messages in real-time (requires websocket mode or polling)."""
    print("Real-time message streaming not yet implemented.")
    print("Use the Slack Socket Mode or set up polling for real-time logging.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Slack messages to a text file (old messages only, no real-time listening)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Log all channels
  python slack_logger.py
  
  # Log only #general and #random
  python slack_logger.py --include general random
  
  # Log all channels except #random and #off-topic
  python slack_logger.py --exclude random off-topic
        """
    )
    parser.add_argument(
        "--include",
        nargs="+",
        dest="include_channels",
        help="Only log these specific channels (space-separated)"
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        dest="exclude_channels",
        help="Exclude these channels from logging (space-separated)"
    )
    
    args = parser.parse_args()
    
    # Log all existing messages with channel filtering
    log_all_messages(
        include_channels=args.include_channels,
        exclude_channels=args.exclude_channels
    )
