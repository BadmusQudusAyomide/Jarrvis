# Jarvis Telegram Bot

A Telegram bot interface for Jarvis AI Assistant.

## Setup

1. **Create a Telegram Bot:**
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Use `/newbot` command
   - Follow the prompts to create your bot
   - Copy the bot token (looks like: `123456789:ABCdefGHIjklMNOpqrSTUvwxyz`)

2. **Set the Token:**
   Edit the `.env` file in the project root and add:
   ```
   TELEGRAM_BOT_TOKEN=your_actual_token_here
   ```

3. **Install Dependencies:**
   ```bash
   pip install python-telegram-bot>=20.0
   ```
   Or if installing all requirements:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the Backend:**
   The Telegram bot requires the Jarvis backend to be running:
   ```bash
   uvicorn app.main:app --port 8080
   ```

5. **Start the Bot:**
   ```bash
   python interfaces/telegram/bot.py
   ```

## Usage

Once running, users can:
- Start the bot with `/start`
- Chat naturally with Jarvis
- Use `/clear` to reset conversation history
- Use `/download <url> [audio_only=true|false] [quality=best|medium|worst]`
- Use `/whoami` to see profile memory summary
- Use `/remember <text>` to save personal facts/preferences
- Use `/forget <text>` to remove a saved note
- Use `/profile` to view stored profile data
- Use `/help` for assistance

Each user gets their own session based on their Telegram user ID.
