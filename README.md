# Log_Bot
Bot to scrape Slack messages into a text file to train an LLM

## Setup

### 1. Create a Slack App
1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name it "Log_Bot" and select your workspace
4. Go to "OAuth & Permissions"
5. Under "Scopes", add these **Bot Token Scopes**:
   - `channels:history` - Read message history
   - `channels:read` - View channels
   - `users:read` - Get user information
6. Scroll to "OAuth Tokens for Your Workspace" and click "Install to Workspace"
7. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

### 2. Set Up Environment
```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with your token
copy .env.example .env
# Edit .env and replace YOUR_TOKEN with your actual bot token
```

### 3. Run the Logger

**Log all messages from all channels:**
```bash
python slack_logger.py
```

**Log only specific channels (e.g., #general and #random):**
```bash
python slack_logger.py --include general random
```

**Log all channels except specific ones (e.g., exclude #random and #off-topic):**
```bash
python slack_logger.py --exclude random off-topic
```

**Log only YOUR messages from all channels:**
```bash
python log_my_messages.py --user-id U123456789
```

**Log YOUR messages from specific channels:**
```bash
python log_my_messages.py --user-id U123456789 --include general announcements
```

**Log YOUR messages from all channels except specific ones:**
```bash
python log_my_messages.py --user-id U123456789 --exclude random off-topic
```

## Features
- **Scrapes old messages only** - No active real-time listening
- **Automatic rate limit handling** - Retries with backoff when Slack rate limits kick in
- Channel filtering: Include or exclude specific channels
- Logs all messages with timestamps
- Captures user information
- Handles pagination for channels with many messages
- Two modes:
  - `slack_logger.py` - Log all messages from everyone
  - `log_my_messages.py` - Log only YOUR messages (great for LLM training on your writing style)

## Output Format
```
[2026-04-16 10:30:45] #general @john: Hello everyone
[2026-04-16 10:31:12] #general @jane: Hi, how's it going?
[2026-04-16 10:32:00] #random @john: Check this out
```

## Notes
- The bot can only access channels it has been invited to
- Make sure to invite the bot to channels you want to scrape messages from
- Thread replies may not be included in this version
- Use `--help` flag to see all available options:
  - `python slack_logger.py --help`
  - `python log_my_messages.py --help`
- **Specify which user's messages to search for:** Use `--user-id U123456789` to search for a specific user's messages instead of the bot account. Find your user ID in Slack by creating a test message and hovering over your profile.
- **Rate Limiting**: If you see "Rate limited by Slack" messages, the script will automatically wait and retry. This is normal for large message volumes.
- To adjust the delay between API calls, edit `RATE_LIMIT_DELAY` in the script (currently 2 seconds)
