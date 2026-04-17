# Discord Ticket Bot

Persistent-button ticket bot built with discord.py.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your **regenerated** bot token.

```bash
python main.py
```

## Usage

1. Invite the bot with `bot` and `applications.commands` scopes and the following permissions: **Manage Channels, View Channels, Send Messages, Read Message History, Manage Roles** (or just Administrator for testing).
2. In your server, run `/setup-tickets` in the channel where the panel should live.
3. Users click **Create Ticket** to open a private channel under the configured category.
4. Staff or the ticket author click **Close Ticket** to delete the channel.

## Env vars

| Key | Purpose |
|-----|---------|
| `DISCORD_TOKEN` | Your bot token (keep secret) |
| `STAFF_ROLE_ID` | Role that can view/close all tickets |
| `CATEGORY_ID` | Category under which ticket channels are created |
