import discord
from discord.ext import commands
from discord.ext import tasks
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

@tasks.loop(minutes=1)
async def award_voice_xp():
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                if member.bot:
                    continue
                voice = member.voice
                if not voice or voice.self_mute or voice.self_deaf or voice.mute or voice.deaf:
                    continue

                gid = str(guild.id)
                uid = str(member.id)

                if gid not in levels:
                    levels[gid] = {}
                if uid not in levels[gid]:
                    levels[gid][uid] = {"xp": 0, "level": 1, "intro_bonus": False}

                user_data = levels[gid][uid]
                user_data["xp"] += 1  # 1 XP per minute in voice

                dummy_channel = guild.system_channel or guild.text_channels[0]
                if dummy_channel:
                    await check_level_up(member, guild, user_data, dummy_channel)

    save_levels()


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
        """🔓 Level 2 unlocked! – you're **gaining traction**!  
You’ve stepped off the sidelines and into the glow-up. You now have access to:

- <#1367147799929684109> – 🌸 Say hi, you gorgeous thing! Tell us about yourself and let us love you for it. This is your red carpet!  
- <#1367160953224958083> – 🎯 Pick your flavour. Pronouns, gender, topics—claim what fits and unlock your side of the server.

🎤 Posting your intro will give you enough XP to unlock Main Chat and the rest of the community. Go on — your spotlight’s waiting."""
    ),

    3: (
        """✨ Level 3 achieved — you’re now a **New Face**!
Welcome to the main community. You now have access to:

- <#1367154656005849088> – 🧃 Pull up a chair and chat! Anything goes (within the rules) — life, laughs, and late-night rambling welcome. Keep it SFW.
- <#1367283783166070939> – 💄 Blush it, beat it, blend it. Tips, looks, reviews, and progress pics—from baby’s first wing to full glam.
- <#1367283861427327079> – 👗 Serve a look. Discuss outfits, styling, trends, and big fashion feelings. Zero judgement, all expression.
- <#1367283982601031730> – 📌 Pin it to win it. Moodboards, aesthetic dumps, dream fits—drop your vision, even if it’s not in your wardrobe (yet).
- <#1368160585677668362> – 💅 Nails, claws, tips, and talons — show off your sets, inspo, polish picks, or press-on finds. Whether you're rocking subtle femme or full glam stiletto, this is your canvas.
- <#1367161557796257813> – 🐸 Unleash chaos. The good kind. Memes, roasts, inside jokes, cursed TikToks—bring it.
- <#1369377952143376424> – 🐾 Show us your floofs, gremlins, scaled companions, or mystery creatures. Pics, stories, chaos—every femme needs a familiar.

Dive in and make yourself at home! 💅🔥"""
    ),

    8: (
        """🔥 Level 8 unlocked — you’re officially a **Regular**!
You’ve earned your heels and your confidence. Welcome to the next tier:

- <#1367154534048333875> – 📸 Show us your look! Hair, makeup, a new outfit—or just your beautiful self. No filters required, just femme realness.
- <#1367280060717072464> – 🦋 Your journey, your pace. A supportive space to talk hormones, changes, dysphoria, euphoria, surgeries, or just vent. No gatekeeping, just sisterhood.
- <#1367169336892063814> – 😈 Wanna get spicy? Start your NSFW journey here by verifying with the mods. Keep it classy and sexy."""
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
    award_voice_xp.start()

SUGGESTION_CHANNEL_ID = 1369680847619227719
SUGGESTION_CATEGORY_ID = 1369680745714548836
REGULAR_ROLE_ID = 1367149083952943186  # "Regular"
SUGGESTION_EMOJI = "👍"
SUGGESTION_THRESHOLD = 5

def slugify_channel_name(text):
    # Clean message into safe channel name
    import re
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', text.lower())
    slug = re.sub(r'\s+', '-', slug).strip('-')
    return slug[:95]  # Max Discord channel name length is 100

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) != SUGGESTION_EMOJI:
        return

    if payload.channel_id != SUGGESTION_CHANNEL_ID:
        return

    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    author = message.author

    # Check if author has Regular role
    member = guild.get_member(author.id)
    if REGULAR_ROLE_ID not in [role.id for role in member.roles]:
        return  # Author is not allowed to make suggestions

    # Count only matching emoji reactions
    for reaction in message.reactions:
        if str(reaction.emoji) == SUGGESTION_EMOJI:
            if reaction.count >= SUGGESTION_THRESHOLD:
                # Create the channel
                channel_name = slugify_channel_name(message.content)
                if discord.utils.get(guild.text_channels, name=channel_name):
                    return  # Channel already exists

                hobby_category = discord.utils.get(guild.categories, id=SUGGESTION_CATEGORY_ID)
                new_channel = await guild.create_text_channel(
                    name=channel_name,
                    category=hobby_category,
                    topic=f"Suggested by {author.display_name}"
                )

                await message.reply(f"💡 Popular idea! I've created <#{new_channel.id}> for you all 🎉")
                break


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
        user_data["intro_bonus"] = True

        # Guarantee level-up to at least level 3
        if user_data["level"] < 3:
            user_data["level"] = 2  # force to level 2
            user_data["xp"] = get_level_xp(2)  # give enough XP to reach 3
        else:
            user_data["xp"] += 250  # fallback bonus if they're already level 3+

        await check_level_up(message.author, message.guild, user_data, message.channel)
    else:
        user_data["xp"] += random.randint(5, 15)
        await check_level_up(message.author, message.guild, user_data, message.channel)

    save_levels()
    await bot.process_commands(message)


LEVEL_UP_CHANNEL_ID = 1369337415629803621  # 💫 #level-up — glow-up announcements live here

async def check_level_up(member, guild, user_data, _):
    gid = str(guild.id)

    while True:
        current_level = user_data["level"]
        required = get_level_xp(current_level)

        if user_data["xp"] < required:
            break

        user_data["level"] += 1
        user_data["xp"] -= required
        new_level = user_data["level"]

        save_levels()  # ✅ Immediately save level changes

        msg = f"{member.mention} is now level {new_level}!"
        if new_level in unlock_messages:
            msg += f"\n{unlock_messages[new_level]}"

        level_channel = guild.get_channel(LEVEL_UP_CHANNEL_ID)
        if level_channel:
            await level_channel.send(msg)

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
                if level_channel:
                    await level_channel.send(f"{member.mention} was given the **{new_role.name}** role!")




@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"Pong! 🏓 {latency}ms")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setlevel(ctx, member: discord.Member, level: int):
    gid = str(ctx.guild.id)
    uid = str(member.id)

    if gid not in levels:
        levels[gid] = {}
    if uid not in levels[gid]:
        levels[gid][uid] = {"xp": 0, "level": 1, "intro_bonus": False}

    levels[gid][uid]["level"] = level
    levels[gid][uid]["xp"] = 0
    save_levels()

    # Send unlock message manually if level is in the unlock list
    if level in unlock_messages:
        msg = f"{member.mention} is now level {level}!\n{unlock_messages[level]}"
        level_channel = ctx.guild.get_channel(LEVEL_UP_CHANNEL_ID)
        if level_channel:
            await level_channel.send(msg)

    # Apply appropriate role for this level
    role_map = {
        2: (FRESH_MEAT, GAINING_TRACTION),
        3: (GAINING_TRACTION, NEW_FACE),
        8: (NEW_FACE, REGULAR)
    }

    if level in role_map:
        old_role_id, new_role_id = role_map[level]
        old_role = ctx.guild.get_role(old_role_id)
        new_role = ctx.guild.get_role(new_role_id)

        if old_role:
            await member.remove_roles(old_role)
        if new_role:
            await member.add_roles(new_role)
            level_channel = ctx.guild.get_channel(LEVEL_UP_CHANNEL_ID)
            if level_channel:
                await level_channel.send(f"{member.mention} was given the **{new_role.name}** role!")

    await ctx.send(f"✅ Set {member.mention}'s level to {level} with 0 XP.")


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
@commands.has_permissions(manage_guild=True)
async def givexp(ctx, member: discord.Member, amount: int):
    """Manually give XP to a member. Admins only."""
    gid = str(ctx.guild.id)
    uid = str(member.id)

    if gid not in levels:
        levels[gid] = {}
    if uid not in levels[gid]:
        levels[gid][uid] = {"xp": 0, "level": 1, "intro_bonus": False}

    user_data = levels[gid][uid]
    user_data["xp"] += amount
    await check_level_up(member, ctx.guild, user_data, ctx.channel)
    save_levels()

    await ctx.send(f"✅ Gave {amount} XP to {member.mention}. They now have {user_data['xp']} XP at level {user_data['level']}.")


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
