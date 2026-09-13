import os
import json
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from openai import OpenAI


# =========================================================
# CONFIGURATION
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN est manquant dans les variables d'environnement.")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY est manquant dans les variables d'environnement.")


# Client OpenAI
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Modèle IA
AI_MODEL = "gpt-5.6-luna"

# Nombre maximum de messages conservés par ticket
MAX_HISTORY = 12

# Nombre de messages du membre avant transfert automatique au staff
DEFAULT_ESCALATION_AFTER = 6


# =========================================================
# CONFIG.JSON
# =========================================================

CONFIG_FILE = "config.json"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


config = load_config()


# =========================================================
# HISTORIQUE IA
# =========================================================

# Exemple :
# {
#     channel_id: [
#         {"role": "user", "content": "..."},
#         {"role": "assistant", "content": "..."}
#     ]
# }

ticket_histories = {}

# Nombre de messages envoyés par le créateur du ticket
ticket_user_messages = {}


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


# =========================================================
# BOT
# =========================================================

class MyBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        self.add_view(TicketView())
        self.add_view(CloseTicketView())

        try:
            synced = await self.tree.sync()
            print(f"{len(synced)} commande(s) slash synchronisée(s).")
        except Exception as e:
            print(f"Erreur synchronisation commandes : {e}")


bot = MyBot()


# =========================================================
# OUTILS
# =========================================================

def get_guild_config(guild_id):
    guild_id = str(guild_id)

    if guild_id not in config:
        config[guild_id] = {}

    return config[guild_id]


def is_ticket_channel(channel):
    return (
        isinstance(channel, discord.TextChannel)
        and channel.topic
        and channel.topic.startswith("ticket:")
    )


def get_ticket_owner_id(channel):
    if not is_ticket_channel(channel):
        return None

    try:
        return int(channel.topic.split(":")[1])
    except Exception:
        return None


def get_staff_role(guild):
    guild_config = get_guild_config(guild.id)

    role_id = guild_config.get("ticket_staff_role")

    if not role_id:
        return None

    return guild.get_role(int(role_id))


# =========================================================
# IA
# =========================================================

AI_SYSTEM_PROMPT = """
Tu es l'assistant IA officiel du serveur Discord SouthLife Rôle-Play.

Ton rôle est d'aider les membres lorsqu'ils ouvrent un ticket.

Règles importantes :

1. Sois poli, calme et professionnel.
2. Réponds en français.
3. Essaie réellement de comprendre le problème avant de proposer une solution.
4. Pose des questions si des informations manquent.
5. Ne prétends jamais être un membre du staff humain.
6. Ne donne pas de décision officielle à la place du staff.
7. Si le problème nécessite une décision humaine, un accès administratif,
   une sanction, une vérification ou une intervention du staff,
   demande l'intervention du staff.
8. Ne demande jamais au membre son mot de passe, son token Discord,
   ses informations bancaires ou d'autres informations secrètes.
9. Si tu penses que le staff doit intervenir immédiatement,
   commence ta réponse par [STAFF].
10. Si tu peux résoudre le problème toi-même, réponds normalement.
11. Reste concis et facile à comprendre.
"""


async def ask_ai(channel, member, user_message):

    channel_id = channel.id

    if channel_id not in ticket_histories:
        ticket_histories[channel_id] = []

    history = ticket_histories[channel_id]

    history.append({
        "role": "user",
        "content": user_message
    })

    # On garde seulement les derniers messages
    history = history[-MAX_HISTORY:]
    ticket_histories[channel_id] = history

    input_messages = []

    for message in history:
        input_messages.append({
            "role": message["role"],
            "content": message["content"]
        })

    try:
        response = await asyncio.to_thread(
            openai_client.responses.create,
            model=AI_MODEL,
            instructions=AI_SYSTEM_PROMPT,
            input=input_messages,
            max_output_tokens=500
        )

        answer = response.output_text.strip()

        if not answer:
            return None, False

        staff_needed = False

        if answer.startswith("[STAFF]"):
            staff_needed = True
            answer = answer.replace("[STAFF]", "", 1).strip()

        history.append({
            "role": "assistant",
            "content": answer
        })

        ticket_histories[channel_id] = history[-MAX_HISTORY:]

        return answer, staff_needed

    except Exception as e:
        print(f"Erreur OpenAI : {e}")
        return None, False


async def send_ai_response(message):

    channel = message.channel
    guild = message.guild

    if not guild:
        return

    if not is_ticket_channel(channel):
        return

    guild_config = get_guild_config(guild.id)

    # IA activée ?
    ai_enabled = guild_config.get("ai_enabled", True)

    if not ai_enabled:
        return

    # Ne répond pas au staff
    staff_role = get_staff_role(guild)

    if staff_role and staff_role in message.author.roles:
        return

    # Compteur des messages du membre
    channel_id = channel.id

    ticket_user_messages[channel_id] = (
        ticket_user_messages.get(channel_id, 0) + 1
    )

    user_message_count = ticket_user_messages[channel_id]

    escalation_after = guild_config.get(
        "ai_escalation_after",
        DEFAULT_ESCALATION_AFTER
    )

    async with channel.typing():

        answer, staff_needed = await ask_ai(
            channel,
            message.author,
            message.content
        )

    if not answer:
        await channel.send(
            "⚠️ Je rencontre actuellement un problème technique. "
            "Un membre du staff pourra prendre le relais."
        )
        return

    # -----------------------------------------------------
    # TRANSFERT STAFF DEMANDÉ PAR L'IA
    # -----------------------------------------------------

    if staff_needed:

        if staff_role:

            embed = discord.Embed(
                title="🤖 Passage au staff",
                description=answer,
                color=discord.Color.orange()
            )

            embed.set_footer(
                text="L'assistant IA recommande l'intervention du staff."
            )

            await channel.send(
                content=staff_role.mention,
                embed=embed
            )

        else:

            await channel.send(
                f"🤖 **Assistant IA**\n\n{answer}\n\n"
                "👮 Le staff doit intervenir sur cette demande."
            )

        return

    # -----------------------------------------------------
    # ESCALADE AUTOMATIQUE APRÈS PLUSIEURS ÉCHANGES
    # -----------------------------------------------------

    if user_message_count >= escalation_after:

        if staff_role:

            embed = discord.Embed(
                title="🤖➡️👮 Intervention du staff",
                description=answer,
                color=discord.Color.orange()
            )

            embed.add_field(
                name="Pourquoi ?",
                value=(
                    "Plusieurs échanges ont eu lieu avec l'assistant. "
                    "Le staff est invité à reprendre le ticket."
                ),
                inline=False
            )

            embed.set_footer(
                text="Assistant IA • SouthLife Rôle-Play"
            )

            await channel.send(
                content=staff_role.mention,
                embed=embed
            )

        else:

            await channel.send(
                f"🤖 **Assistant IA**\n\n{answer}\n\n"
                "👮 Plusieurs échanges ont eu lieu. "
                "Il serait préférable qu'un membre du staff intervienne."
            )

        return

    # -----------------------------------------------------
    # RÉPONSE NORMALE DE L'IA
    # -----------------------------------------------------

    embed = discord.Embed(
        title="🤖 Assistant SouthLife",
        description=answer,
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="Assistant IA • SouthLife Rôle-Play"
    )

    await channel.send(embed=embed)


# =========================================================
# TICKET : OUVRIR
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ouvrir un ticket",
        emoji="🎫",
        style=discord.ButtonStyle.green,
        custom_id="open_ticket"
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild
        member = interaction.user

        guild_config = get_guild_config(guild.id)

        category_id = guild_config.get("ticket_category")
        staff_role_id = guild_config.get("ticket_staff_role")

        if not category_id:
            await interaction.response.send_message(
                "❌ Le système de tickets n'est pas encore configuré.",
                ephemeral=True
            )
            return

        category = guild.get_channel(int(category_id))

        if not category:
            await interaction.response.send_message(
                "❌ La catégorie des tickets est introuvable.",
                ephemeral=True
            )
            return

        # Vérification ticket déjà existant
        for channel in guild.text_channels:

            if (
                channel.topic
                and channel.topic == f"ticket:{member.id}"
            ):
                await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket ouvert : {channel.mention}",
                    ephemeral=True
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True
            )
        }

        # Ajouter le staff
        if staff_role_id:

            staff_role = guild.get_role(int(staff_role_id))

            if staff_role:

                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        channel = await guild.create_text_channel(
            name=f"ticket-{member.id}",
            category=category,
            overwrites=overwrites,
            topic=f"ticket:{member.id}",
            reason=f"Ticket ouvert par {member}"
        )

        # Initialisation historique IA
        ticket_histories[channel.id] = []
        ticket_user_messages[channel.id] = 0

        embed = discord.Embed(
            title="🎫 Ticket ouvert",
            description=(
                f"Bonjour {member.mention} !\n\n"
                "Bienvenue dans ton ticket.\n\n"
                "🤖 **Un assistant IA peut maintenant t'aider.**\n"
                "Explique clairement ton problème et il essaiera "
                "de te proposer une solution.\n\n"
                "👮 Si le problème nécessite l'intervention du staff, "
                "le ticket pourra être transmis à un membre du staff.\n\n"
                "Un membre du staff peut également intervenir à tout moment."
            ),
            color=discord.Color.green()
        )

        embed.set_footer(
            text="SouthLife Rôle-Play • Système de tickets"
        )

        await channel.send(
            content=member.mention,
            embed=embed,
            view=CloseTicketView()
        )

        await interaction.response.send_message(
            f"✅ Ton ticket a été créé : {channel.mention}",
            ephemeral=True
        )


# =========================================================
# TICKET : FERMER
# =========================================================

class CloseTicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fermer le ticket",
        emoji="🔒",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel
        guild = interaction.guild
        member = interaction.user

        owner_id = get_ticket_owner_id(channel)

        if owner_id is None:
            await interaction.response.send_message(
                "❌ Ce salon n'est pas un ticket.",
                ephemeral=True
            )
            return

        staff_role = get_staff_role(guild)

        is_owner = member.id == owner_id
        is_staff = staff_role and staff_role in member.roles

        if not is_owner and not is_staff:

            await interaction.response.send_message(
                "❌ Tu n'as pas la permission de fermer ce ticket.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔒 Fermeture du ticket dans quelques secondes..."
        )

        # Nettoyage mémoire
        ticket_histories.pop(channel.id, None)
        ticket_user_messages.pop(channel.id, None)

        await asyncio.sleep(3)

        try:
            await channel.delete(
                reason=f"Ticket fermé par {member}"
            )
        except Exception as e:
            print(f"Erreur suppression ticket : {e}")


# =========================================================
# CONFIGURATION PRINCIPALE
# =========================================================

class ConfigView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="Bienvenue",
        emoji="👋",
        style=discord.ButtonStyle.primary
    )
    async def welcome_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tu dois être administrateur.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="👋 Configuration bienvenue",
            description=(
                "Choisis le salon dans lequel les messages de bienvenue "
                "doivent être envoyés."
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=WelcomeConfigView()
        )

    @discord.ui.button(
        label="Tickets",
        emoji="🎫",
        style=discord.ButtonStyle.success
    )
    async def tickets_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tu dois être administrateur.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎫 Configuration des tickets",
            description=(
                "Configure les éléments nécessaires au système de tickets."
            ),
            color=discord.Color.green()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=TicketConfigView()
        )

    @discord.ui.button(
        label="Assistant IA",
        emoji="🤖",
        style=discord.ButtonStyle.secondary
    )
    async def ai_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tu dois être administrateur.",
                ephemeral=True
            )
            return

        guild_config = get_guild_config(interaction.guild.id)

        enabled = guild_config.get("ai_enabled", True)
        threshold = guild_config.get(
            "ai_escalation_after",
            DEFAULT_ESCALATION_AFTER
        )

        status = "🟢 Activé" if enabled else "🔴 Désactivé"

        embed = discord.Embed(
            title="🤖 Assistant IA",
            description=(
                f"**État :** {status}\n\n"
                f"**Transfert automatique :** après "
                f"**{threshold} messages** du membre.\n\n"
                "L'IA répond uniquement dans les tickets et peut "
                "demander l'intervention du staff."
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=AIConfigView()
        )


# =========================================================
# CONFIGURATION BIENVENUE
# =========================================================

class WelcomeChannelSelect(discord.ui.ChannelSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisir le salon de bienvenue",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):

        selected_channel = self.values[0]

        guild_config = get_guild_config(interaction.guild.id)

        guild_config["welcome_channel"] = selected_channel.id

        save_config(config)

        await interaction.response.send_message(
            f"✅ Salon de bienvenue enregistré : {selected_channel.mention}",
            ephemeral=True
        )


class WelcomeConfigView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

        self.add_item(WelcomeChannelSelect())


# =========================================================
# CONFIGURATION TICKETS
# =========================================================

class TicketCategorySelect(discord.ui.ChannelSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisir la catégorie des tickets",
            channel_types=[discord.ChannelType.category],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):

        selected = self.values[0]

        guild_config = get_guild_config(interaction.guild.id)

        guild_config["ticket_category"] = selected.id

        save_config(config)

        await interaction.response.send_message(
            f"✅ Catégorie enregistrée : **{selected.name}**",
            ephemeral=True
        )


class TicketChannelSelect(discord.ui.ChannelSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisir le salon du panneau ticket",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):

        selected = self.values[0]

        guild_config = get_guild_config(interaction.guild.id)

        guild_config["ticket_channel"] = selected.id

        save_config(config)

        await interaction.response.send_message(
            f"✅ Salon du panneau enregistré : {selected.mention}",
            ephemeral=True
        )


class TicketStaffRoleSelect(discord.ui.RoleSelect):

    def __init__(self):
        super().__init__(
            placeholder="Choisir le rôle Staff",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):

        selected = self.values[0]

        guild_config = get_guild_config(interaction.guild.id)

        guild_config["ticket_staff_role"] = selected.id

        save_config(config)

        await interaction.response.send_message(
            f"✅ Rôle Staff enregistré : {selected.mention}",
            ephemeral=True
        )


class SaveTicketConfigButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="Enregistrer",
            emoji="💾",
            style=discord.ButtonStyle.success
        )

    async def callback(self, interaction: discord.Interaction):

        guild_config = get_guild_config(interaction.guild.id)

        category_ok = guild_config.get("ticket_category")
        channel_ok = guild_config.get("ticket_channel")
        staff_ok = guild_config.get("ticket_staff_role")

        if not category_ok or not channel_ok or not staff_ok:

            await interaction.response.send_message(
                "❌ Tu dois sélectionner la catégorie, "
                "le salon du panneau et le rôle Staff.",
                ephemeral=True
            )
            return

        save_config(config)

        await interaction.response.send_message(
            "✅ Configuration des tickets enregistrée !",
            ephemeral=True
        )


class TicketConfigView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

        self.add_item(TicketCategorySelect())
        self.add_item(TicketChannelSelect())
        self.add_item(TicketStaffRoleSelect())
        self.add_item(SaveTicketConfigButton())


# =========================================================
# CONFIGURATION IA
# =========================================================

class AIToggleButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="Activer / Désactiver",
            emoji="🤖",
            style=discord.ButtonStyle.primary
        )

    async def callback(self, interaction: discord.Interaction):

        guild_config = get_guild_config(interaction.guild.id)

        current = guild_config.get("ai_enabled", True)

        guild_config["ai_enabled"] = not current

        save_config(config)

        new_status = (
            "🟢 activé"
            if guild_config["ai_enabled"]
            else "🔴 désactivé"
        )

        await interaction.response.send_message(
            f"✅ Assistant IA {new_status}.",
            ephemeral=True
        )


class AIThresholdButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="Changer le seuil",
            emoji="🔢",
            style=discord.ButtonStyle.secondary
        )

    async def callback(self, interaction: discord.Interaction):

        await interaction.response.send_modal(
            AIThresholdModal()
        )


class AIConfigView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

        self.add_item(AIToggleButton())
        self.add_item(AIThresholdButton())


class AIThresholdModal(discord.ui.Modal, title="Seuil de transfert IA"):

    threshold = discord.ui.TextInput(
        label="Nombre de messages",
        placeholder="Exemple : 6",
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):

        try:
            value = int(self.threshold.value)

            if value < 1 or value > 20:
                raise ValueError

        except ValueError:

            await interaction.response.send_message(
                "❌ Choisis un nombre entre 1 et 20.",
                ephemeral=True
            )
            return

        guild_config = get_guild_config(interaction.guild.id)

        guild_config["ai_escalation_after"] = value

        save_config(config)

        await interaction.response.send_message(
            f"✅ L'IA transférera automatiquement au staff "
            f"après **{value} messages** du membre.",
            ephemeral=True
        )


# =========================================================
# COMMANDE /CONFIG
# =========================================================

@bot.tree.command(
    name="config",
    description="Configurer le bot SouthLife"
)
@app_commands.checks.has_permissions(administrator=True)
async def config_command(interaction: discord.Interaction):

    embed = discord.Embed(
        title="⚙️ Configuration SouthLife",
        description=(
            "Bienvenue dans le panneau de configuration.\n\n"
            "👋 **Bienvenue**\n"
            "Configure le salon de bienvenue.\n\n"
            "🎫 **Tickets**\n"
            "Configure la catégorie, le panneau et le rôle Staff.\n\n"
            "🤖 **Assistant IA**\n"
            "Configure l'assistant automatique des tickets."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="SouthLife Rôle-Play • Configuration"
    )

    await interaction.response.send_message(
        embed=embed,
        view=ConfigView(),
        ephemeral=True
    )


@config_command.error
async def config_command_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(error, app_commands.errors.MissingPermissions):

        await interaction.response.send_message(
            "❌ Tu dois être administrateur pour utiliser cette commande.",
            ephemeral=True
        )


# =========================================================
# COMMANDE /TICKETPANEL
# =========================================================

@bot.tree.command(
    name="ticketpanel",
    description="Envoyer le panneau de création de tickets"
)
@app_commands.checks.has_permissions(administrator=True)
async def ticketpanel_command(interaction: discord.Interaction):

    guild_config = get_guild_config(interaction.guild.id)

    channel_id = guild_config.get("ticket_channel")

    if not channel_id:

        await interaction.response.send_message(
            "❌ Configure d'abord le salon du panneau avec `/config`.",
            ephemeral=True
        )
        return

    channel = interaction.guild.get_channel(int(channel_id))

    if not channel:

        await interaction.response.send_message(
            "❌ Le salon configuré est introuvable.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Tickets",
        description=(
            "Bienvenue dans l'onglet \"besoin d'aide\" de SouthLife Rôle-Play.\n\n"

            "Si vous avez besoin d'aide vous êtes au bon endroit ! "
            "Cependant si votre aide ne nécessite pas forcément un ticket "
            "Discord, faites un report en jeu et attendez un staff.\n\n"

            "Lorsque vous créez un ticket merci d'être le plus précis "
            "possible dans votre démarche.\n\n"

            "Cela facilitera la compréhension du staff et la rapidité "
            "de résolution de votre demande.\n\n"

            "À noter que nous sommes des humains, pas des robots. "
            "Merci donc de patienter sagement qu'un staff vous réponde.\n\n"

            "(Les pings abusifs seront sanctionnés.)\n\n"

            "De plus la politesse ne fait pas de mal, un bonjour ou un "
            "merci est bienvenu.\n\n"

            "En espérant pouvoir régler tous vos soucis."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="Système de tickets • SouthLife Rôle-Play"
    )

    await channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        f"✅ Panneau envoyé dans {channel.mention}.",
        ephemeral=True
    )


@ticketpanel_command.error
async def ticketpanel_command_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(error, app_commands.errors.MissingPermissions):

        await interaction.response.send_message(
            "❌ Tu dois être administrateur pour utiliser cette commande.",
            ephemeral=True
        )


# =========================================================
# BIENVENUE + ROLE CIVILS
# =========================================================

@bot.event
async def on_member_join(member):

    guild = member.guild

    # -----------------------------------------------------
    # ROLE CIVILS
    # -----------------------------------------------------

    civils_role = discord.utils.get(
        guild.roles,
        name="・Civils"
    )

    if civils_role:

        try:

            await member.add_roles(
                civils_role,
                reason="Attribution automatique du rôle Civil"
            )

            print(
                f"Rôle ・Civils donné à {member}."
            )

        except Exception as e:

            print(
                f"Impossible de donner le rôle ・Civils : {e}"
            )

    else:

        print(
            f"Rôle ・Civils introuvable sur {guild.name}."
        )

    # -----------------------------------------------------
    # MESSAGE DE BIENVENUE
    # -----------------------------------------------------

    guild_config = get_guild_config(guild.id)

    welcome_channel_id = guild_config.get(
        "welcome_channel"
    )

    if not welcome_channel_id:
        return

    channel = guild.get_channel(
        int(welcome_channel_id)
    )

    if not channel:
        return

    embed = discord.Embed(
        title="👋 Bienvenue !",
        description=(
            f"Bienvenue {member.mention} sur "
            f"**{guild.name}** !\n\n"
            "Nous sommes heureux de t'accueillir parmi nous. "
            "Amuse-toi bien sur SouthLife Rôle-Play !"
        ),
        color=discord.Color.green()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.set_footer(
        text=f"Membre n°{guild.member_count}"
    )

    try:
        await channel.send(embed=embed)

    except Exception as e:
        print(
            f"Erreur message bienvenue : {e}"
        )


# =========================================================
# MESSAGES
# =========================================================

@bot.event
async def on_message(message):

    # Ignorer les bots
    if message.author.bot:
        return

    # IA dans les tickets
    if message.guild and is_ticket_channel(message.channel):

        await send_ai_response(message)

    # Commandes préfixées éventuelles
    await bot.process_commands(message)


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"✅ Connecté en tant que {bot.user} "
        f"(ID: {bot.user.id})"
    )

    print(
        f"🤖 IA : {AI_MODEL}"
    )

    print(
        "🎫 Système de tickets chargé."
    )

    print(
        "👋 Système de bienvenue chargé."
    )


# =========================================================
# LANCEMENT
# =========================================================

bot.run(TOKEN)
