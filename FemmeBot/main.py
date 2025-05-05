import discord
from discord.ext import commands
from discord.ui import View, Button
import os
import json
import random
from flask import Flask
from threading import Thread
from datetime import datetime

# === Flask keep-alive server ===
app = Flask('')

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

prefix = os.environ.get("BOT_PREFIX", "!")
bot = commands.Bot(command_prefix=prefix, intents=intents)
print(f"✅ Bot prefix set to: {prefix}")

cooldowns = {}

# === Load & Save JSON ===
def load_json(filename, default={}):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return default

def save_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

levels = load_json("levels.json")
settings = load_json("settings.json")
tickets = load_json("tickets.json")
reaction_roles = load_json("reaction_roles.json")

def save_levels():
    save_json(levels, "levels.json")

def save_settings():
    save_json(settings, "settings.json")

def save_tickets():
    save_json(tickets, "tickets.json")

def save_reaction_roles():
    save_json(reaction_roles, "reaction_roles.json")

# === XP Logic ===
def get_level_xp(level):
    return 5 * (level**2) + 50 * level + 100

role_rewards = {2: "Gaining Traction", 3: "New Face", 8: "Regular"}

unlock_messages = {
    2: (
        "🎉 You're now Level 2 (**Gaining Traction**)! You should now see "
        "<#1367154605079441489> (**Introductions**) and <#1367154633989554206> (**Grab Your Roles**) — "
        "come say hi and choose your interests! 💖"
    ),

    3: (
        "✨ Level 3 achieved — you’re now a **New Face**! Welcome to the main community. "
        "You now have access to:\n"
        "- <#1367154656005849088> main chat\n"
        "- <#1367283783166070939> makeup\n"
        "- <#1367283861427327079> fashion\n"
        "- <#1367283982601031730> outfit inspo\n"
        "- <#1367161557796257813> memes and shitposting\n"
        "Dive in and make yourself at home! 💅"
    ),

    8: (
        "😈 You’ve reached Level 8 and earned the **Regular** role! You now have access to "
        "<#1367154534048333875> (**SFW Selfies**) 💃\n"
        "Feeling bold? Head to <#1367169336892063814> to verify for NSFW access. 🔥"
    )
}

INTRO_CHANNEL_ID = 1367154605079441489
FRESH_MEAT = 1367821643342151710
GAINING_TRACTION = 1367148340873138307
NEW_FACE = 1367148896140394607
REGULAR = 1367149083952943186

# === Ticket Button View ===
class TicketButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton())

class TicketButton(Button):
    def __init__(self):
        super().__init__(label="Open NSFW Verification Ticket",
                         style=discord.ButtonStyle.green,
                         emoji="📩",
                         custom_id="nsfw_ticket_button")

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        gid = str(guild.id)
        uid = str(user.id)

        if gid in tickets and uid in tickets[gid]:
            await interaction.response.send_message("You already have an open ticket!", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True)
        }

        mod_role = discord.utils.get(guild.roles, name="Mod")
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        mod_category = discord.utils.get(guild.categories, id=1367155319473442866)
        channel = await guild.create_text_channel(
            name=f"ticket-{user.display_name.lower().replace(' ', '-')}",
            overwrites=overwrites,
            category=mod_category,
            topic=f"NSFW verification for {user.display_name}")

        if gid not in tickets:
            tickets[gid] = {}
        tickets[gid][uid] = {"channel_id": channel.id, "display_name": user.display_name}
        save_tickets()

        await channel.send(
            f"👋 Hi {user.mention}! Please upload your verification photo here.\n"
            f"A mod will review it shortly. Once done, they'll close the ticket with a ✅.",
            allowed_mentions=discord.AllowedMentions(users=True))
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        verification_log_channel = guild.get_channel(1367167338696278146)
        if verification_log_channel and mod_role:
            await verification_log_channel.send(
                f"{mod_role.mention} A new NSFW ticket has been opened: {channel.mention}")

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}")
    keep_alive()
    bot.add_view(TicketButtonView())

@bot.event
async def on_member_join(member):
    role = member.guild.get_role(FRESH_MEAT)
    if role:
        await member.add_roles(role)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    now = datetime.utcnow()
    key = f"{guild_id}-{user_id}"

    if key in cooldowns and (now - cooldowns[key]).total_seconds() < 60:
        await bot.process_commands(message)
        return

    cooldowns[key] = now

    if guild_id not in levels:
        levels[guild_id] = {}
    if user_id not in levels[guild_id]:
        levels[guild_id][user_id] = {"xp": 0, "level": 1, "intro_bonus": False}

    user_data = levels[guild_id][user_id]
    if message.channel.id == INTRO_CHANNEL_ID and not user_data.get("intro_bonus"):
        user_data["xp"] += 250
        user_data["intro_bonus"] = True
    else:
        user_data["xp"] += random.randint(5, 15)

    await check_level_up(message.author, message.guild, user_data, message.channel)
    save_levels()
    await bot.process_commands(message)

async def check_level_up(member, guild, user_data, channel):
    gid = str(guild.id)
    current_level = user_data["level"]
    required = get_level_xp(current_level)

    if user_data["xp"] >= required:
        user_data["level"] += 1
        user_data["xp"] -= required
        new_level = user_data["level"]

        msg = f"{member.mention} is now level {new_level}!"
        if new_level in unlock_messages:
            msg += f"\n{unlock_messages[new_level]}"
        await channel.send(msg)

        old_new = {
            2: (FRESH_MEAT, GAINING_TRACTION),
            3: (GAINING_TRACTION, NEW_FACE),
            8: (NEW_FACE, REGULAR)
        }
        if new_level in old_new:
            old_role_id, new_role_id = old_new[new_level]
            old_role = guild.get_role(old_role_id)
            new_role = guild.get_role(new_role_id)
            if old_role:
                await member.remove_roles(old_role)
            if new_role:
                await member.add_roles(new_role)
                await channel.send(f"{member.mention} was given the **{new_role.name}** role!")

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"Pong! 🏓 {latency}ms")

@bot.command()
async def leaderboard(ctx):
    gid = str(ctx.guild.id)
    if gid not in levels:
        await ctx.send("No data yet.")
        return

    sorted_users = sorted(levels[gid].items(),
                          key=lambda item: (item[1]["level"], item[1]["xp"]),
                          reverse=True)[:10]

    embed = discord.Embed(title="🏆 Leaderboard", colour=discord.Colour.gold())
    for i, (uid, data) in enumerate(sorted_users, start=1):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"<User {uid}>"
        embed.add_field(name=f"{i}. {name}",
                        value=f"Level {data['level']} – {data['xp']} XP",
                        inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def level(ctx, member: discord.Member = None):
    member = member or ctx.author
    gid = str(ctx.guild.id)
    uid = str(member.id)

    if gid in levels and uid in levels[gid]:
        data = levels[gid][uid]
        current = data['level']
        xp = data['xp']
        needed = get_level_xp(current)
        await ctx.send(
            f"{member.mention} is level {current} with {xp}/{needed} XP.")
    else:
        await ctx.send(f"{member.mention} hasn’t earned any XP yet.")

@bot.command()
@commands.has_permissions(administrator=True)
async def introbonus(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id not in levels:
        await ctx.send("No data found.")
        return

    matching = []
    for user_id, data in levels[guild_id].items():
        if data.get("intro_bonus"):
            member = ctx.guild.get_member(int(user_id))
            if member:
                matching.append(member.display_name)

    if matching:
        await ctx.send("✅ Users with `intro_bonus = True`:\n" + "\n".join(matching))
    else:
        await ctx.send("No users have claimed the intro bonus yet.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    if amount < 1:
        await ctx.send("Please enter a number greater than 0.")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        confirm = await ctx.send(f"🧹 Deleted {len(deleted)-1} messages.")
        await confirm.delete(delay=5)
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to manage messages here.")
    except Exception as e:
        await ctx.send(f"⚠️ Error: {e}")

@bot.command()
async def setup(ctx, subcommand=None, *args):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You don’t have permission to use this command.")
        return

    if subcommand == "rules" and len(args) == 2:
        message_id = int(args[0])
        xp = int(args[1])
        settings[str(ctx.guild.id)] = {
            "rules_message_id": message_id,
            "rules_xp": xp
        }
        save_settings()
        await ctx.send(
            f"✅ Rules message set to `{message_id}` with XP boost `{xp}`.")

    elif subcommand == "ticketbutton":
        target_channel = bot.get_channel(1367169336892063814)
        if target_channel:
            view = TicketButtonView()
            await target_channel.send(
    "**NSFW Verification**\nClick below to create a private ticket for verification 📨",
    view=view)

            await ctx.send("✅ Ticket button sent to #nsfw-verification.")
        else:
            await ctx.send("❌ Couldn't find the verification channel.")

    elif subcommand == "reactionrole" and len(args) >= 3:
        try:
            message_id = args[0]
            emoji = args[1]
            role_name = ' '.join(args[2:])

            role = discord.utils.get(ctx.guild.roles, name=role_name)
            if not role:
                await ctx.send(
                    f"Role '{role_name}' not found. Please create it first.")
                return

            message = await ctx.channel.fetch_message(int(message_id))

            guild_id = str(ctx.guild.id)
            if guild_id not in reaction_roles:
                reaction_roles[guild_id] = {}
            if message_id not in reaction_roles[guild_id]:
                reaction_roles[guild_id][message_id] = {}

            reaction_roles[guild_id][message_id][emoji] = role_name
            await message.add_reaction(emoji)

            save_reaction_roles()
            await ctx.send(f"✅ Reaction role added: {emoji} → {role_name}")
        except Exception as e:
            await ctx.send(f"Error setting reaction role: {e}")

    elif subcommand == "reactionroles" and args and args[0] == "list":
        guild_id = str(ctx.guild.id)
        if guild_id not in reaction_roles or not reaction_roles[guild_id]:
            await ctx.send("No reaction roles configured.")
            return

        embed = discord.Embed(title="📌 Reaction Roles",
                              color=discord.Color.purple())
        for msg_id, mappings in reaction_roles[guild_id].items():
            lines = [f"{emoji} → {role}" for emoji, role in mappings.items()]
            embed.add_field(name=f"Message ID: {msg_id}",
            value="".join(lines),
            inline=False)

        await ctx.send(embed=embed)

    else:
       await ctx.send(
    "Usage:\n"
    "`!setup rules <message_id> <xp>`\n"
    "`!setup ticketbutton`\n"
    "`!setup reactionrole <message_id> <emoji> <role name>`\n"
    "`!setup reactionroles list`")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if guild_id in settings:
        rules_msg_id = settings[guild_id].get("rules_message_id")
        xp = settings[guild_id].get("rules_xp", 0)

        if payload.message_id == rules_msg_id:
            if guild_id not in levels:
                levels[guild_id] = {}
            if str(payload.user_id) not in levels[guild_id]:
              levels[guild_id][str(payload.user_id)] = {"xp": 0, "level": 1, "intro_bonus": False}


            user_data = levels[guild_id][str(payload.user_id)]
            user_data["xp"] += xp

            guild = bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)

            if member:
                dummy_channel = guild.system_channel or guild.text_channels[0]
                await check_level_up(member, guild, user_data, dummy_channel)

            save_levels()

    if guild_id in reaction_roles and message_id in reaction_roles[guild_id]:
        mapping = reaction_roles[guild_id][message_id]
        if emoji in mapping:
            guild = bot.get_guild(payload.guild_id)
            role = discord.utils.get(guild.roles, name=mapping[emoji])
            member = guild.get_member(payload.user_id)
            if role and member:
                await member.add_roles(role)

    if str(payload.emoji) == "✅":
        guild = bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        gid = str(guild.id)
        uid = str(payload.user_id)

        if channel and channel.name.startswith("ticket-"):
            await channel.send("✅ Ticket closed. This channel will now be deleted.")

            ticket_info = tickets.get(gid, {}).get(uid, {})
            display_name = ticket_info.get("display_name", "unknown")

            verification_log_channel = discord.utils.get(
                guild.text_channels, id=1367167338696278146)
            if verification_log_channel:
                await verification_log_channel.send(
                    f"✅ Ticket for **{display_name}** has been closed.")

            await channel.delete()

            if gid in tickets and uid in tickets[gid]:
                del tickets[gid][uid]
                save_tickets()

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return

    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if guild_id in reaction_roles and message_id in reaction_roles[guild_id]:
        mapping = reaction_roles[guild_id][message_id]
        if emoji in mapping:
            guild = bot.get_guild(payload.guild_id)
            role = discord.utils.get(guild.roles, name=mapping[emoji])
            member = guild.get_member(payload.user_id)
            if role and member:
                await member.remove_roles(role)

# === Launch the bot ===
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN not found in environment variables.")
else:
    bot.run(TOKEN)
