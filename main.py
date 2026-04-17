import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1459406213660807331"))
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "1494489789830004787"))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


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
        if not channel.name.startswith("ticket-"):
            await interaction.response.send_message(
                "This isn't a ticket channel.", ephemeral=True
            )
            return

        is_staff = any(r.id == STAFF_ROLE_ID for r in interaction.user.roles)
        is_owner = channel.topic and str(interaction.user.id) in (channel.topic or "")
        if not (is_staff or is_owner):
            await interaction.response.send_message(
                "Only staff or the ticket author can close this ticket.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Ticket closed by {interaction.user.mention}. Deleting in 5 seconds..."
        )
        import asyncio
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to delete this channel.", ephemeral=True
            )


class CreateTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:create",
        emoji="🎫",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        existing = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
        if existing:
            await interaction.response.send_message(
                f"You already have an open ticket: {existing.mention}",
                ephemeral=True,
            )
            return

        category = guild.get_channel(CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Ticket category is not configured correctly. Please contact an admin.",
                ephemeral=True,
            )
            return

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
                name=f"ticket-{user.name.lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket owner: {user.id}",
                reason=f"Ticket created by {user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to create channels.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Ticket Opened",
            description=(
                f"Hello {user.mention}, thanks for opening a ticket.\n"
                f"A member of {staff_role.mention if staff_role else 'staff'} "
                f"will be with you shortly.\n\n"
                f"Press the button below to close this ticket when you're done."
            ),
            color=discord.Color.blurple(),
        )
        await channel.send(
            content=f"{user.mention} {staff_role.mention if staff_role else ''}",
            embed=embed,
            view=CloseTicketView(),
        )

        await interaction.response.send_message(
            f"Your ticket has been created: {channel.mention}", ephemeral=True
        )


@bot.event
async def on_ready():
    bot.add_view(CreateTicketView())
    bot.add_view(CloseTicketView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Sync failed: {e}")
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.tree.command(name="setup-tickets", description="Post the ticket creation panel in this channel.")
@app_commands.default_permissions(manage_guild=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Support Tickets",
        description="Need help? Click the button below to open a private ticket with our staff team.",
        color=discord.Color.blurple(),
    )
    await interaction.channel.send(embed=embed, view=CreateTicketView())
    await interaction.response.send_message("Ticket panel posted.", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Put it in your .env file.")
    bot.run(TOKEN)
