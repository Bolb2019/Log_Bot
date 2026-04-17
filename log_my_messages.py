"""
Slack personal message logger - Captures only YOUR messages and saves them to a text file.
Useful for training an LLM on your writing style.
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
OUTPUT_FILE = "my_messages.txt"
RATE_LIMIT_DELAY = 2  # 2 second delay between API calls (increased for safety)
CHANNEL_DELAY = 1.5  # Delay after processing each channel
USER_CACHE = {}  # Cache user names to avoid repeated API calls
 
 
def handle_rate_limit(retry_after=None):
    """Handle Slack API rate limiting with exponential backoff."""
    delay = int(retry_after) if retry_after else RATE_LIMIT_DELAY
    print(f"Rate limited by Slack. Waiting {delay} second(s)...")
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
 
 
def get_bot_user_id():
    """Get the user ID of the bot/app."""
    try:
        result = api_call_with_retry(client.auth_test)
        return result["user_id"]
    except SlackApiError as e:
        print(f"Error getting bot user ID: {e}")
        return None
 
 
def get_all_channels():
    """Fetch all public and private channels the user is a member of."""
    try:
        channels = []
        result = api_call_with_retry(
            client.conversations_list,
            limit=100,
            exclude_archived=True,
            types="public_channel,private_channel"
        )
        # Only include channels where user is a member
        channels.extend([c for c in result["channels"] if c.get("is_member")])
       
        while result.get("response_metadata", {}).get("next_cursor"):
            result = api_call_with_retry(
                client.conversations_list,
                limit=100,
                exclude_archived=True,
                types="public_channel,private_channel",
                cursor=result["response_metadata"]["next_cursor"]
            )
            channels.extend([c for c in result["channels"] if c.get("is_member")])
       
        return channels
    except SlackApiError as e:
        print(f"Error fetching channels: {e}")
        return []
 
 
def get_messages_from_channel(channel_id, user_id, limit=1000, oldest=0):
    """Fetch messages from a specific channel by a specific user.
   
    Args:
        channel_id: The channel ID to fetch from
        user_id: Filter messages by this user ID
        limit: Maximum number of messages to fetch
        oldest: Unix timestamp - only fetch messages on or after this time
    """
    try:
        messages = []
        result = api_call_with_retry(client.conversations_history, channel=channel_id, limit=100, oldest=oldest)
        messages.extend([m for m in result["messages"] if m.get("user") == user_id])
       
        # Pagination
        while result.get("has_more") and len(messages) < limit:
            result = api_call_with_retry(
                client.conversations_history,
                channel=channel_id,
                limit=100,
                oldest=oldest,
                cursor=result.get("response_metadata", {}).get("next_cursor")
            )
            messages.extend([m for m in result["messages"] if m.get("user") == user_id])
       
        return messages[:limit]
    except SlackApiError as e:
        print(f"Error fetching messages from {channel_id}: {e}")
        return []
 
 
def format_message(message, channel_name):
    """Format a message for writing to file."""
    text = message.get("text", "")
    return f"{text}\n"
 
 
def log_my_messages(include_channels=None, exclude_channels=None, user_id=None):
    """Log messages to a file.
   
    Args:
        include_channels: List of channel names to include (only these will be logged)
        exclude_channels: List of channel names to exclude
        user_id: Slack user ID to search for messages from (if None, uses bot account)
    """
    print("Starting Slack message logging...")
    print("Mode: Scraping old messages only (not listening for new ones)")
    print(f"Rate limit protection: {RATE_LIMIT_DELAY}s delay between API calls")
   
    # Get user ID
    if user_id:
        print(f"Searching for messages from user ID: {user_id}")
    else:
        user_id = get_bot_user_id()
        if not user_id:
            print("Failed to get user ID")
            return
        print(f"Searching for messages from user ID: {user_id}")
   
    # Calculate timestamp for 1 year and 5 months ago (approximately 17 months)
    oldest_date = datetime.now() - timedelta(days=365 + 150)  # 515 days
    oldest = oldest_date.timestamp()
    cutoff_str = oldest_date.strftime("%Y-%m-%d")
    print(f"Fetching messages from {cutoff_str} onward.\n")
   
    channels = get_all_channels()
    print(f"Found {len(channels)} channels available")
   
    # Apply channel filtering
    channels = filter_channels(channels, include_channels, exclude_channels)
    print(f"Searching in {len(channels)} channels after filtering...")
    print(f"Estimated time: ~{len(channels) * (CHANNEL_DELAY + 2)} seconds\n")
   
    if not channels:
        print("No channels to process after filtering!")
        return
   
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        total_messages = 0
        for idx, channel in enumerate(channels, 1):
            channel_id = channel["id"]
            channel_name = channel["name"]
           
            print(f"[{idx}/{len(channels)}] Processing #{channel_name}...", end="", flush=True)
           
            messages = get_messages_from_channel(channel_id, user_id, oldest=oldest)
            if messages:
                print(f" {len(messages)} messages found")
                total_messages += len(messages)
               
                for message in reversed(messages):  # Chronological order
                    formatted = format_message(message, channel_name)
                    f.write(formatted)
            else:
                print(" (no messages)")
           
            # Delay between channels to avoid rate limiting
            if idx < len(channels):
                time.sleep(CHANNEL_DELAY)
   
    print(f"\nLogging complete! Found {total_messages} of the user's messages")
    print(f"Messages saved to {OUTPUT_FILE}")
 
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Slack messages to a text file (old messages only, no real-time listening)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Log messages from a specific user (replace U123456789 with actual user ID)
  python log_my_messages.py --user-id U123456789
 
  # Log messages from a specific user from #general only
  python log_my_messages.py --user-id U123456789 --include general
 
  # Log messages from a user, exclude certain channels
  python log_my_messages.py --user-id U123456789 --exclude random off-topic
 
  # Log bot account messages (default if no --user-id specified)
  python log_my_messages.py
        """
    )
    parser.add_argument(
        "--include",
        nargs="+",
        dest="include_channels",
        help="Only log messages from these specific channels (space-separated)"
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        dest="exclude_channels",
        help="Exclude these channels from logging (space-separated)"
    )
    parser.add_argument(
        "--user-id",
        dest="user_id",
        help="Slack user ID to search for messages from (e.g., 'U123456789'). If not provided, uses bot account."
    )
   
    args = parser.parse_args()
   
    log_my_messages(
        include_channels=args.include_channels,
        exclude_channels=args.exclude_channels,
        user_id=args.user_id
    )