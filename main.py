import os
import io
import re
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1459406213660807331"))
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "1494489789830004787"))
TRANSCRIPT_CHANNEL_ID = int(os.getenv("TRANSCRIPT_CHANNEL_ID", "0"))

OPEN_EMOJI = "🟢"
CLOSED_EMOJI = "🔴"

EMBED_COLOR = 0xFFD464
WEBSITE_URL = "https://fantasysmp.net/"

COUNTER_FILE = Path(os.getenv("COUNTER_PATH", "counter.json"))
counter_lock = asyncio.Lock()


def _load_counter() -> int:
    if COUNTER_FILE.exists():
        try:
            return int(json.loads(COUNTER_FILE.read_text()).get("count", 0))
        except Exception:
            return 0
    return 0


def _save_counter(n: int) -> None:
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_FILE.write_text(json.dumps({"count": n}))


async def next_ticket_number() -> int:
    async with counter_lock:
        n = _load_counter() + 1
        _save_counter(n)
        return n


async def generate_transcript_text(channel: discord.TextChannel) -> str:
    lines = [
        f"Transcript of #{channel.name}",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 60,
        "",
    ]
    first = True
    async for msg in channel.history(limit=None, oldest_first=True):
        if first:
            first = False
            continue
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
        author = str(msg.author)
        body = msg.content or ""
        for emb in msg.embeds:
            parts = []
            if emb.title:
                parts.append(emb.title)
            if emb.description:
                parts.append(emb.description)
            if parts:
                body += "\n[Embed] " + " | ".join(parts)
        for att in msg.attachments:
            body += f"\n[Attachment: {att.filename} | {att.url}]"
        if not body.strip():
            continue
        lines.append(f"[{ts}] {author}:")
        for line in body.splitlines():
            lines.append(f"  {line}")
        lines.append("")
    return "\n".join(lines)


def _transcript_file(text: str, name: str) -> discord.File:
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=name)

TICKET_TYPES = {
    "support": {
        "label": "Support",
        "emoji": "🛠️",
        "prefix": "support",
        "title": "Support Ticket",
        "intro": (
            "Thanks for opening a support ticket on **FantasySMP**. "
            "To help us get you sorted quickly, please include:\n\n"
            "• What you need help with (in-game, website, account, payment, etc.)\n"
            "• Your **in-game username**\n"
            "• Any error messages or screenshots\n"
            "• Steps you've already tried\n\n"
            "⚠️ **Heads up:** this ticket system isn't a live chat. Our team "
            "will review your message and respond as soon as possible. "
            "You'll get a notification here when we reply."
        ),
    },
    "report": {
        "label": "Report User",
        "emoji": "🚩",
        "prefix": "report",
        "title": "Report a Player",
        "intro": (
            "Thanks for reporting. To act on this, we'll need:\n\n"
            "• The offender's **in-game username** (and Discord, if applicable)\n"
            "• What they did (cheating, griefing, chat, etc.)\n"
            "• **Proof**: screenshots, clips, or timestamps\n"
            "• When it happened (approximate time is fine)\n\n"
            "⚠️ **Heads up:** reports are reviewed privately and aren't live. "
            "We won't share outcomes publicly, but you'll be notified here "
            "once we've looked into it."
        ),
    },
    "question": {
        "label": "Question",
        "emoji": "❓",
        "prefix": "question",
        "title": "General Question",
        "intro": (
            "Ask away! The more specific the question, the faster we can answer.\n\n"
            "• If it's about a feature, command, or rank, say which one\n"
            "• If it's about the website, include the page URL\n\n"
            f"🌐 Website: {WEBSITE_URL}\n\n"
            "⚠️ **Heads up:** this isn't a live chat. We'll reply here when "
            "a staff member is free. You'll be notified when we respond."
        ),
    },
    "appeal": {
        "label": "Appeal",
        "emoji": "⚖️",
        "prefix": "appeal",
        "title": "Ban / Punishment Appeal",
        "intro": (
            "To review your appeal, please include:\n\n"
            "• Your **in-game username**\n"
            "• What you were punished for (if you know)\n"
            "• Roughly when it happened\n"
            "• Why you believe it should be reviewed / what you'd do differently\n\n"
            "⚠️ **Heads up:** appeals are reviewed privately by staff and "
            "aren't live. Pinging or arguing won't speed things up. We'll "
            "respond here once a decision is made."
        ),
    },
}

intents = discord.Intents.default()
intents.message_content = True  # Required to detect staff-application questions in tickets
bot = commands.Bot(command_prefix="!", intents=intents)


# ───── STAFF APPLICATION TUTORIAL ─────
STAFF_TUTORIAL_AVATAR = (
    "https://cdn.discordapp.com/attachments/1500458209553420370/1500462706745151671/test.png"
    "?ex=69f8864a&is=69f734ca&hm=a7a2752617e2623841a88ac02808e043905c0ae80d014305ff0ae1b0c7fa1cc8&animated=true"
)
STAFF_TUTORIAL_IMAGE = (
    "https://cdn.discordapp.com/attachments/1500458209553420370/1500461409165770853/Frame_24.png"
    "?ex=69f88515&is=69f73395&hm=cf782085f2f204e676b62342546c5c4ab69ea648402ac737550a3163f56addbd&animated=true"
)

# Channels that have already received an auto staff-tutorial reply
_staff_tutorial_sent: set[int] = set()


def build_staff_tutorial_embed() -> discord.Embed:
    embed = discord.Embed(
        title="<:mod:1463152741655515250> Join the Staff Team!",
        description=(
            "If you want to apply for staff please use our website: \n"
            "**[[Click here to apply for staff]](https://fantasysmp.net/staff)**\n\n"
            "**Step 1: **\n"
            "- Open the link pasted above.\n"
            "**Step 2:**\n"
            "-Scroll down till you see the section **Join the Team**.\n"
            "**Step 3:**\n"
            "- Select one of the categories.\n"
            "**Step 4:**\n"
            "- Complete the Survey and hit **'Submit Application'**"
        ),
        color=16762645,
    )
    embed.set_image(url=STAFF_TUTORIAL_IMAGE)
    embed.set_thumbnail(url=STAFF_TUTORIAL_AVATAR)
    return embed


# Patterns that look like "how can I apply for staff / become a moderator / etc."
_STAFF_ROLE_WORDS = r"(?:staff|moderator|mod|admin(?:istrator)?|helper|developer|dev|builder|coordinator|team)"
_STAFF_TRIGGER_PATTERNS = [
    re.compile(rf"\bapply\b.*\bfor\b.*{_STAFF_ROLE_WORDS}\b", re.IGNORECASE),
    re.compile(rf"\bapply\b.*\b(?:as|to(?:\s+be)?)\b.*{_STAFF_ROLE_WORDS}\b", re.IGNORECASE),
    re.compile(rf"\b(?:how|where|can\s+i|how\s+do\s+i|how\s+can\s+i)\b.*\bapply\b", re.IGNORECASE),
    re.compile(rf"\b(?:how|where|can\s+i|how\s+do\s+i|how\s+can\s+i)\b.*\b(?:become|join|be(?:\s+a)?|get)\b.*{_STAFF_ROLE_WORDS}\b", re.IGNORECASE),
    re.compile(rf"\b(?:join|be\s+part\s+of)\b.*\b(?:the\s+)?(?:staff|team)\b", re.IGNORECASE),
    re.compile(rf"\bstaff\s+application\b", re.IGNORECASE),
    re.compile(rf"\bapply\s+(?:for\s+)?{_STAFF_ROLE_WORDS}\b", re.IGNORECASE),
]


def looks_like_staff_question(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in _STAFF_TRIGGER_PATTERNS)


def _parse_owner_id(topic: str) -> int | None:
    if "Ticket owner:" not in topic:
        return None
    try:
        return int(topic.split("Ticket owner:")[1].split("|")[0].strip())
    except Exception:
        return None


def _is_staff(member: discord.Member) -> bool:
    return any(r.id == STAFF_ROLE_ID for r in member.roles)


async def _auto_delete_ephemeral(interaction: discord.Interaction, delay: int = 15):
    await asyncio.sleep(delay)
    try:
        await interaction.delete_original_response()
    except Exception:
        pass


async def _resolve_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.HTTPException):
        return None


async def _perform_close(channel: discord.TextChannel, closer: discord.Member):
    owner_id = _parse_owner_id(channel.topic or "")
    if owner_id is not None:
        owner_target = None
        for target in list(channel.overwrites.keys()):
            if isinstance(target, (discord.Member, discord.User)) and target.id == owner_id:
                owner_target = target
                break
        if owner_target is None:
            try:
                owner_target = await bot.fetch_user(owner_id)
            except discord.HTTPException as e:
                print(f"[close] fetch_user failed: {e}")
        if owner_target is not None:
            try:
                await channel.set_permissions(
                    owner_target,
                    view_channel=True,
                    read_message_history=True,
                    send_messages=False,
                    add_reactions=False,
                    send_messages_in_threads=False,
                    create_public_threads=False,
                    create_private_threads=False,
                    attach_files=False,
                    embed_links=False,
                )
            except Exception as e:
                print(f"[close] set_permissions failed: {e}")

    if channel.name.startswith(OPEN_EMOJI):
        new_name = CLOSED_EMOJI + channel.name[len(OPEN_EMOJI):]
    elif not channel.name.startswith(CLOSED_EMOJI):
        new_name = CLOSED_EMOJI + channel.name
    else:
        new_name = channel.name
    try:
        await channel.edit(name=new_name[:95])
    except discord.HTTPException:
        pass

    closed_embed = discord.Embed(
        description=(
            f"Ticket Closed by {closer.mention}\n\n"
            "**Staff Ticket Actions**"
        ),
        color=discord.Color(EMBED_COLOR),
    )
    await channel.send(embed=closed_embed, view=ClosedTicketView())


async def _perform_reopen(channel: discord.TextChannel, opener: discord.Member):
    owner_id = _parse_owner_id(channel.topic or "")
    if owner_id is not None:
        owner_target = None
        for target in list(channel.overwrites.keys()):
            if isinstance(target, (discord.Member, discord.User)) and target.id == owner_id:
                owner_target = target
                break
        if owner_target is None:
            try:
                owner_target = await bot.fetch_user(owner_id)
            except discord.HTTPException as e:
                print(f"[reopen] fetch_user failed: {e}")
        if owner_target is not None:
            try:
                await channel.set_permissions(
                    owner_target,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    add_reactions=True,
                )
            except Exception as e:
                print(f"[reopen] set_permissions failed: {e}")

    if channel.name.startswith(CLOSED_EMOJI):
        try:
            await channel.edit(name=OPEN_EMOJI + channel.name[len(CLOSED_EMOJI):])
        except discord.HTTPException:
            pass

    reopen_embed = discord.Embed(
        description=f"Ticket Reopened by {opener.mention}",
        color=discord.Color(EMBED_COLOR),
    )
    await channel.send(embed=reopen_embed)


async def _perform_transcript(channel: discord.TextChannel, requester: discord.Member) -> str:
    owner_id = _parse_owner_id(channel.topic or "")
    text = await generate_transcript_text(channel)
    filename = f"transcript-{channel.name}.txt"
    status = []

    if owner_id:
        try:
            owner = await bot.fetch_user(owner_id)
            dm_embed = discord.Embed(
                title="Your ticket transcript",
                description=(
                    "Thanks for contacting **FantasySMP** support. "
                    "A transcript of your ticket is attached for your records."
                ),
                color=discord.Color(EMBED_COLOR),
            )
            await owner.send(embed=dm_embed, file=_transcript_file(text, filename))
            status.append(f"DMed to <@{owner_id}>")
        except discord.Forbidden:
            status.append(f"❌ Could not DM <@{owner_id}> (DMs disabled)")
        except discord.HTTPException as e:
            status.append(f"❌ DM failed: {e}")

    if TRANSCRIPT_CHANNEL_ID:
        archive = channel.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
        if archive is not None:
            archive_embed = discord.Embed(
                title=f"Transcript: {channel.name}",
                description=(
                    f"**Author:** <@{owner_id}>\n"
                    f"**Generated by:** {requester.mention}"
                ),
                color=discord.Color(EMBED_COLOR),
                timestamp=datetime.now(timezone.utc),
            )
            try:
                await archive.send(
                    embed=archive_embed,
                    file=_transcript_file(text, filename),
                )
                status.append(f"Archived in {archive.mention}")
            except discord.HTTPException as e:
                status.append(f"❌ Archive failed: {e}")

    return "\n".join(status) if status else "Transcript generated (no destinations configured)."


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
        emoji="🔒",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        topic = channel.topic or ""
        if _parse_owner_id(topic) is None:
            await interaction.response.send_message(
                "This isn't a ticket channel.", ephemeral=True
            )
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                "Only staff can close tickets.", ephemeral=True
            )
            return
        if channel.name.startswith(CLOSED_EMOJI):
            await interaction.response.send_message(
                "This ticket is already closed.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="Close this ticket?",
            description="Click **Close Ticket** again to confirm, or Cancel.",
            color=discord.Color(EMBED_COLOR),
        )
        await interaction.response.send_message(
            embed=embed, view=ConfirmCloseView(), ephemeral=True
        )


class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        topic = channel.topic or ""
        owner_id = _parse_owner_id(topic)
        if owner_id is None:
            await interaction.response.edit_message(content="Not a ticket.", embed=None, view=None)
            return
        if not _is_staff(interaction.user):
            await interaction.response.edit_message(
                content="Only staff can close tickets.", embed=None, view=None
            )
            return

        await interaction.response.edit_message(
            content="Ticket closed.", embed=None, view=None
        )
        await _perform_close(channel, interaction.user)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Cancelled.", embed=None, view=None
        )


class ClosedTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Transcript",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:transcript",
        emoji="📄",
    )
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                "Only staff can generate transcripts.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            summary = await _perform_transcript(interaction.channel, interaction.user)
        except Exception as e:
            await interaction.edit_original_response(
                content=f"Failed to generate transcript: {e}"
            )
            return
        await interaction.edit_original_response(content=summary)

    @discord.ui.button(
        label="Open",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:reopen",
        emoji="🔓",
    )
    async def reopen(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        topic = channel.topic or ""
        owner_id = _parse_owner_id(topic)
        if owner_id is None:
            await interaction.response.send_message("Not a ticket.", ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                "Only staff can reopen tickets.", ephemeral=True
            )
            return
        if not channel.name.startswith(CLOSED_EMOJI):
            await interaction.response.send_message(
                "This ticket is already open.", ephemeral=True
            )
            return

        await interaction.response.edit_message(embeds=[], view=None, content=None)
        try:
            await _perform_reopen(channel, interaction.user)
        except Exception as e:
            print(f"[reopen button] _perform_reopen raised: {e!r}")
            try:
                await interaction.followup.send(
                    f"Failed to reopen: `{e}`", ephemeral=True
                )
            except Exception:
                pass

    @discord.ui.button(
        label="Delete",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:delete",
        emoji="⛔",
    )
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                "Only staff can delete tickets.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Deleting in 5 seconds..."
        )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(
                reason=f"Ticket deleted by {interaction.user}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to delete this channel.", ephemeral=True
            )


async def open_ticket(interaction: discord.Interaction, kind: str):
    await interaction.response.defer(ephemeral=True, thinking=True)

    guild = interaction.guild
    user = interaction.user
    info = TICKET_TYPES[kind]

    category = guild.get_channel(CATEGORY_ID)
    if category is None or not isinstance(category, discord.CategoryChannel):
        await interaction.edit_original_response(
            content="Ticket category is not configured correctly. Please contact an admin."
        )
        return

    MAX_TICKETS_PER_USER = 3
    user_tickets = [
        ch for ch in category.text_channels
        if ch.topic and f"Ticket owner: {user.id}" in ch.topic
    ]
    if len(user_tickets) >= MAX_TICKETS_PER_USER:
        mentions = ", ".join(ch.mention for ch in user_tickets)
        await interaction.edit_original_response(
            content=(
                f"You already have {len(user_tickets)} open tickets "
                f"(max {MAX_TICKETS_PER_USER}): {mentions}"
            )
        )
        return

    number = await next_ticket_number()
    safe_name = "".join(c for c in user.name.lower() if c.isalnum() or c in "-_") or "user"
    channel_name = f"{OPEN_EMOJI}{number:04d}-{safe_name}-{kind}"[:95]

    staff_role = guild.get_role(STAFF_ROLE_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True,
        ),
    }
    if staff_role is not None:
        overwrites[staff_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        )

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Ticket owner: {user.id} | Type: {kind}",
            reason=f"{info['label']} ticket created by {user}",
        )
    except discord.Forbidden:
        await interaction.edit_original_response(
            content="I don't have permission to create channels."
        )
        return
    except discord.HTTPException as e:
        await interaction.edit_original_response(
            content=f"Failed to create channel: {e}"
        )
        return

    embed = discord.Embed(
        title=f"{info['emoji']} {info['title']}",
        description=info["intro"],
        color=discord.Color(EMBED_COLOR),
    )
    embed.set_footer(text=f"Opened by {user}")

    staff_mention = f"||{staff_role.mention}||" if staff_role else ""
    await channel.send(
        content=f"{user.mention} {staff_mention}".strip(),
        embed=embed,
        view=CloseTicketView(),
        allowed_mentions=discord.AllowedMentions(roles=True, users=True),
    )

    await interaction.edit_original_response(
        content=f"Your ticket has been created: {channel.mention}"
    )
    asyncio.create_task(_auto_delete_ephemeral(interaction))


class CreateTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support", style=discord.ButtonStyle.primary, emoji="🛠️", custom_id="ticket:support")
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_ticket(interaction, "support")

    @discord.ui.button(label="Question", style=discord.ButtonStyle.danger, emoji="💬", custom_id="ticket:question")
    async def btn_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_ticket(interaction, "question")

    @discord.ui.button(label="Report User", style=discord.ButtonStyle.secondary, emoji="🚩", custom_id="ticket:report")
    async def btn_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_ticket(interaction, "report")

    @discord.ui.button(label="Appeal", style=discord.ButtonStyle.success, emoji="⚖️", custom_id="ticket:appeal")
    async def btn_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_ticket(interaction, "appeal")


@bot.event
async def on_ready():
    bot.add_view(CreateTicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(ClosedTicketView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Sync failed: {e}")
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    # Don't react to bots (including ourselves)
    if message.author.bot:
        return
    # Only fire inside ticket channels
    channel = message.channel
    if not isinstance(channel, discord.TextChannel):
        return
    if not channel.topic or _parse_owner_id(channel.topic) is None:
        return
    # Only respond once per ticket channel
    if channel.id in _staff_tutorial_sent:
        return
    if not looks_like_staff_question(message.content):
        return
    _staff_tutorial_sent.add(channel.id)
    try:
        await channel.send(
            content="**If you want to join the staff team follow the next steps!**",
            embed=build_staff_tutorial_embed(),
            reference=message,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as e:
        print(f"[stafftut auto] send failed: {e}")
        # Allow retry on failure
        _staff_tutorial_sent.discard(channel.id)


@bot.tree.command(name="stafftut", description="Send the staff application tutorial in this channel.")
@app_commands.default_permissions(manage_messages=True)
async def cmd_stafftut(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not _is_staff(interaction.user):
        await interaction.response.send_message(
            "Only staff can use this command.", ephemeral=True
        )
        return
    try:
        await interaction.channel.send(
            content="**If you want to join the staff team follow the next steps!**",
            embed=build_staff_tutorial_embed(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(
            f"Failed to send tutorial: {e}", ephemeral=True
        )
        return
    # Mark this ticket as already covered so the auto-reply doesn't double up
    if isinstance(interaction.channel, discord.TextChannel):
        _staff_tutorial_sent.add(interaction.channel.id)
    await interaction.response.send_message("Sent.", ephemeral=True)
    asyncio.create_task(_auto_delete_ephemeral(interaction, delay=5))


@bot.tree.command(name="setup-tickets", description="Post the ticket creation panel in this channel.")
@app_commands.default_permissions(manage_guild=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="FantasySMP Support",
        description=(
            "Need a hand on **FantasySMP**? Pick the category that matches "
            "your issue and we'll open a private ticket with our staff team.\n\n"
            "**Support**: general help (account, in-game, payments)\n"
            "**Report User**: report a player (bring proof)\n"
            "**Question**: ask us anything about the server or website\n"
            "**Appeal**: appeal a ban or punishment\n\n"
            f"🌐 Website: {WEBSITE_URL}"
        ),
        color=discord.Color(EMBED_COLOR),
    )
    await interaction.channel.send(embed=embed, view=CreateTicketView())
    await interaction.response.send_message("Ticket panel posted.", ephemeral=True)


@bot.tree.command(name="close", description="Close this ticket.")
async def cmd_close(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel) or _parse_owner_id(channel.topic or "") is None:
        await interaction.response.send_message(
            "This isn't a ticket channel.", ephemeral=True
        )
        return
    if not _is_staff(interaction.user):
        await interaction.response.send_message(
            "Only staff can close tickets.", ephemeral=True
        )
        return
    if channel.name.startswith(CLOSED_EMOJI):
        await interaction.response.send_message(
            "This ticket is already closed.", ephemeral=True
        )
        return
    await interaction.response.send_message("Closing ticket...", ephemeral=True)
    await _perform_close(channel, interaction.user)


@bot.tree.command(name="open", description="Reopen this closed ticket.")
async def cmd_open(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel) or _parse_owner_id(channel.topic or "") is None:
        await interaction.response.send_message(
            "This isn't a ticket channel.", ephemeral=True
        )
        return
    if not _is_staff(interaction.user):
        await interaction.response.send_message(
            "Only staff can reopen tickets.", ephemeral=True
        )
        return
    if not channel.name.startswith(CLOSED_EMOJI):
        await interaction.response.send_message(
            "This ticket is already open.", ephemeral=True
        )
        return
    await interaction.response.send_message("Reopening ticket...", ephemeral=True)
    await _perform_reopen(channel, interaction.user)


@bot.tree.command(name="transcript", description="Generate a transcript for this ticket.")
async def cmd_transcript(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel) or _parse_owner_id(channel.topic or "") is None:
        await interaction.response.send_message(
            "This isn't a ticket channel.", ephemeral=True
        )
        return
    if not _is_staff(interaction.user):
        await interaction.response.send_message(
            "Only staff can generate transcripts.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        summary = await _perform_transcript(channel, interaction.user)
    except Exception as e:
        await interaction.edit_original_response(
            content=f"Failed to generate transcript: {e}"
        )
        return
    await interaction.edit_original_response(content=summary)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Put it in your .env file.")
    bot.run(TOKEN)
