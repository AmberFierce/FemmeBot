import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import os
import asyncpg
import random
from flask import Flask
from threading import Thread
from datetime import datetime

# === Flask keep-alive server ===
app = Flask(__name__)

@app.route('/')
def home():
    return "FemmeBot is alive!"

def run_web():
    app.run(host='0.0.0.0', port=3000)

def keep_alive():
    Thread(target=run_web).start()

# === Bot setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix=os.getenv("BOT_PREFIX", "!"), intents=intents)
print(f"✅ Bot prefix set to: {bot.command_prefix}")

cooldowns = {}
reaction_roles = {}
DATABASE_URL = os.getenv("DATABASE_URL")

# === PostgreSQL helpers ===
async def connect_db():
    return await asyncpg.connect(DATABASE_URL)

async def get_user_data(guild_id, user_id):
    conn = await connect_db()
    row = await conn.fetchrow("""
        SELECT xp, level, intro_bonus FROM user_levels
        WHERE user_id = $1 AND guild_id = $2;
    """, str(user_id), str(guild_id))
    await conn.close()
    if row:
        return dict(row)
    return {"xp": 0, "level": 1, "intro_bonus": False}

async def set_user_data(guild_id, user_id, xp, level, intro_bonus):
    conn = await connect_db()
    await conn.execute("""
        INSERT INTO user_levels (user_id, guild_id, xp, level, intro_bonus)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, guild_id)
        DO UPDATE SET xp = $3, level = $4, intro_bonus = $5;
    """, str(user_id), str(guild_id), xp, level, intro_bonus)
    await conn.close()

async def add_xp(guild_id, user_id, amount):
    data = await get_user_data(guild_id, user_id)
    new_xp = data["xp"] + amount
    await set_user_data(guild_id, user_id, new_xp, data["level"], data["intro_bonus"])
    return new_xp, data["level"], data["intro_bonus"]

async def force_intro_bonus(guild_id, user_id):
    data = await get_user_data(guild_id, user_id)
    if not data["intro_bonus"]:
        new_level = max(data["level"], 2)
        new_xp = get_level_xp(2) if new_level == 2 else data["xp"] + 250
        await set_user_data(guild_id, user_id, new_xp, new_level, True)
        return True
    return False

async def add_reaction_role(guild_id, message_id, emoji, role_name):
    conn = await connect_db()
    await conn.execute("""
        INSERT INTO reaction_roles (guild_id, message_id, emoji, role_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id, message_id, emoji) DO UPDATE
        SET role_name = EXCLUDED.role_name;
    """, str(guild_id), str(message_id), emoji, role_name)
    await conn.close()

async def load_reaction_roles():
    conn = await connect_db()
    rows = await conn.fetch("SELECT guild_id, message_id, emoji, role_name FROM reaction_roles;")
    await conn.close()
    result = {}
    for row in rows:
        g_id = row["guild_id"]
        m_id = row["message_id"]
        emoji = row["emoji"]
        role = row["role_name"]
        result.setdefault(g_id, {}).setdefault(m_id, {})[emoji] = role
    return result

# === XP logic ===
def get_level_xp(level):
    return 5 * (level**2) + 50 * level + 100

# === Level Role Definitions ===
level_roles = {
    2: ("GAINING_TRACTION_ROLE_ID", "🔓 Level 2 unlocked! – you're **gaining traction**!\nYou now have access to intros and pronoun roles."),
    3: ("NEW_FACE_ROLE_ID", "✨ Level 3 achieved — you’re now a **New Face**!\nAccess to main chat and beauty/style channels granted."),
    8: ("REGULAR_ROLE_ID", "🔥 Level 8 unlocked — you’re officially a **Regular**!\nWelcome to selfies and NSFW verification.")
}

# === Level Up Check ===
async def check_level_up(member, guild):
    user_id = member.id
    guild_id = guild.id
    data = await get_user_data(guild_id, user_id)
    xp = data["xp"]
    level = data["level"]
    intro_bonus = data["intro_bonus"]

    level_channel_id = os.getenv("LEVEL_UP_CHANNEL_ID")
    level_channel = guild.get_channel(int(level_channel_id)) if level_channel_id else None

    while xp >= get_level_xp(level):
        xp -= get_level_xp(level)
        level += 1

        await set_user_data(guild_id, user_id, xp, level, intro_bonus)

        msg = f"{member.mention} is now level {level}!"

        if level in level_roles:
            role_env, unlock_msg = level_roles[level]
            msg += f"\n{unlock_msg}"

            old_level = level - 1
            if old_level in level_roles:
                old_role_id = os.getenv(level_roles[old_level][0])
                if old_role_id:
                    old_role = guild.get_role(int(old_role_id))
                    if old_role:
                        await member.remove_roles(old_role)

            new_role_id = os.getenv(role_env)
            if new_role_id:
                new_role = guild.get_role(int(new_role_id))
                if new_role:
                    await member.add_roles(new_role)
                    msg += f"\n{member.mention} was given the **{new_role.name}** role!"

        if level_channel:
            await level_channel.send(msg)

# === Message Event for XP/Bonus ===
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    guild_id = message.guild.id
    user_id = message.author.id
    now = datetime.utcnow()
    key = f"{guild_id}-{user_id}"

    if key in cooldowns and (now - cooldowns[key]).total_seconds() < 60:
        await bot.process_commands(message)
        return

    cooldowns[key] = now

    intro_channel = os.getenv("INTRO_CHANNEL_ID")
    if intro_channel and message.channel.id == int(intro_channel):
        bonus_given = await force_intro_bonus(guild_id, user_id)
        if bonus_given:
            await check_level_up(message.author, message.guild)
    else:
        await add_xp(guild_id, user_id, random.randint(5, 15))
        await check_level_up(message.author, message.guild)

    await bot.process_commands(message)

# === Ready Event ===
@bot.event
async def on_ready():
    global reaction_roles
    keep_alive()
    bot.add_view(TicketButtonView())
    reaction_roles = await load_reaction_roles()
    print("✅ Reaction roles loaded from database.")
    print(f"Bot is ready as {bot.user}")

# === Member Join Event ===
@bot.event
async def on_member_join(member):
    role_id = os.getenv("FRESH_MEAT_ROLE_ID")
    if role_id:
        role = member.guild.get_role(int(role_id))
        if role:
            await member.add_roles(role)

# === Setup Command and Ticket System ===

class TicketButton(Button):
    def __init__(self):
        super().__init__(
            label="Open NSFW Verification Ticket",
            style=discord.ButtonStyle.green,
            emoji="📩",
            custom_id="nsfw_ticket_button"
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        mod_category_id = os.getenv("MOD_CATEGORY_ID")
        mod_role_name = os.getenv("MOD_ROLE_NAME")
        log_channel_id = os.getenv("NSFW_VERIFICATION_LOG_ID")

        if not mod_category_id:
            await interaction.response.send_message("❌ Ticket category ID not configured.", ephemeral=True)
            return

        category = discord.utils.get(guild.categories, id=int(mod_category_id))
        if not category:
            await interaction.response.send_message("❌ Ticket category not found.", ephemeral=True)
            return

        existing_channel = discord.utils.get(category.channels, name=f"ticket-{user.id}")
        if existing_channel:
            await interaction.response.send_message(f"📬 You already have a ticket open: {existing_channel.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True)
        }

        mod_role = discord.utils.get(guild.roles, name=mod_role_name)
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{user.id}",
            category=category,
            overwrites=overwrites,
            topic=f"NSFW verification for {user.display_name}"
        )

        await channel.send(
    f"👋 Hi {user.mention}! Please upload your verification photo here.\\nA mod will review it shortly. Once done, they'll close the ticket with a ✅.",
    allowed_mentions=discord.AllowedMentions(users=True)
)

        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        if log_channel_id:
            log_channel = guild.get_channel(int(log_channel_id))
            if log_channel and mod_role:
                await log_channel.send(f"{mod_role.mention} A new NSFW ticket has been opened: {channel.mention}")

class TicketButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton())

# === Setup Command ===
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx, subcommand=None, *args):
    if subcommand == "ticketbutton":
        target_channel_id = os.getenv("NSFW_VERIFICATION_CHANNEL_ID")
        if target_channel_id:
            target_channel = bot.get_channel(int(target_channel_id))
            if target_channel:
                view = TicketButtonView()
                await target_channel.send(
                    "**NSFW Verification**\\nClick below to create a private ticket for verification 📨",
                    view=view
                )
                await ctx.send("✅ Ticket button sent.")
            else:
                await ctx.send("❌ Could not find target channel.")
        else:
            await ctx.send("❌ NSFW_VERIFICATION_CHANNEL_ID not set.")

    elif subcommand == "reactionrole" and len(args) >= 3:
        message_id = args[0]
        emoji = args[1]
        role_name = " ".join(args[2:])
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            await ctx.send(f"Role '{role_name}' not found.")
            return

        try:
            message = await ctx.channel.fetch_message(int(message_id))
            reaction_roles.setdefault(str(ctx.guild.id), {}).setdefault(message_id, {})[emoji] = role_name
            await add_reaction_role(ctx.guild.id, message_id, emoji, role_name)
            await message.add_reaction(emoji)
            await ctx.send(f"✅ Reaction role added: {emoji} → {role_name}")
        except Exception as e:
            await ctx.send(f"❌ Failed to add reaction role: {e}")
    else:
        await ctx.send("Usage:\n!setup ticketbutton\n!setup reactionrole <message_id> <emoji> <role name>")

# === Reaction Role and Suggestion Events ===

@bot.event
async def on_raw_reaction_add(payload):
    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    member = guild.get_member(payload.user_id)
    emoji = str(payload.emoji)
    message_id = str(payload.message_id)
    guild_id = str(payload.guild_id)

    # Ticket close
    if channel and channel.name.startswith("ticket-") and emoji == "✅":
        await channel.send("✅ Ticket closed. This channel will now be deleted.")
        log_channel_id = os.getenv("NSFW_VERIFICATION_LOG_ID")
        if log_channel_id:
            log_channel = guild.get_channel(int(log_channel_id))
            if log_channel:
                await log_channel.send(f"✅ Ticket for **{member.display_name}** has been closed.")
        await channel.delete()
        return

    # Reaction roles
    if guild_id in reaction_roles and message_id in reaction_roles[guild_id]:
        role_name = reaction_roles[guild_id][message_id].get(emoji)
        if role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            if role and member:
                await member.add_roles(role)
                print(f"✅ Added role {role_name} to {member.display_name}")

    # Suggestion threshold
    if emoji == "👍":
        suggestion_channel = os.getenv("SUGGESTION_CHANNEL_ID")
        suggestion_category = os.getenv("SUGGESTION_CATEGORY_ID")
        suggestion_threshold = int(os.getenv("SUGGESTION_THRESHOLD", 5))

        if suggestion_channel and suggestion_category and str(payload.channel_id) == suggestion_channel:
            message = await channel.fetch_message(payload.message_id)
            author = guild.get_member(message.author.id)

            for reaction in message.reactions:
                if str(reaction.emoji) == "👍" and reaction.count >= suggestion_threshold:
                    slug = message.content.lower().replace(" ", "-")[:95]
                    existing = discord.utils.get(guild.text_channels, name=slug)
                    if existing:
                        return
                    category = discord.utils.get(guild.categories, id=int(suggestion_category))
                    new_channel = await guild.create_text_channel(name=slug, category=category)
                    await message.reply(f"💡 Popular idea! I've created <#{new_channel.id}> for you all 🎉")
                    break

@bot.event
async def on_raw_reaction_remove(payload):
    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)
    if guild_id in reaction_roles and message_id in reaction_roles[guild_id]:
        role_name = reaction_roles[guild_id][message_id].get(emoji)
        if role_name:
            guild = bot.get_guild(payload.guild_id)
            role = discord.utils.get(guild.roles, name=role_name)
            member = guild.get_member(payload.user_id)
            if role and member:
                await member.remove_roles(role)

# === Final Launch ===
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_TOKEN not found in environment variables.")
    else:
        bot.run(TOKEN)
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! 🏓 {round(bot.latency * 1000)}ms")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setlevel(ctx, member: discord.Member, level: int):
    await set_user_data(ctx.guild.id, member.id, 0, level, False)
    await check_level_up(member, ctx.guild)
    await ctx.send(f"✅ Set {member.mention}'s level to {level} and applied rewards/messages if applicable.")

@bot.command()
async def level(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = await get_user_data(ctx.guild.id, member.id)
    current = data['level']
    xp = data['xp']
    needed = get_level_xp(current)
    await ctx.send(f"{member.mention} is level {current} with {xp}/{needed} XP.")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def givexp(ctx, member: discord.Member, amount: int):
    xp, level, _ = await add_xp(ctx.guild.id, member.id, amount)
    await ctx.send(f"✅ Gave {amount} XP to {member.mention}. They now have {xp} XP at level {level}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def introbonus(ctx):
    found = []
    for member in ctx.guild.members:
        if member.bot:
            continue
        data = await get_user_data(ctx.guild.id, member.id)
        if data.get("intro_bonus"):
            found.append(member.display_name)
    if found:
        await ctx.send("✅ Users with `intro_bonus = True`:\n" + "\n".join(found))
    else:
        await ctx.send("No users have claimed the intro bonus yet.")
