import os
import json
import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")

# ==========================================
# CONFIGURATION
# ==========================================

TICKET_CATEGORY = "🎫-tickets"
TICKET_CHANNEL = "📞丨contact"
STAFF_ROLE = "Staff"

CONFIG_FILE = "config.json"


# ==========================================
# SAUVEGARDE DES CONFIGURATIONS
# ==========================================

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)


config = load_config()


# ==========================================
# INTENTS
# ==========================================

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ==========================================
# SYSTÈME DE TICKETS
# ==========================================

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

        # Vérifier les tickets existants
        for channel in guild.text_channels:

            if channel.topic == f"ticket:{member.id}":

                await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket : {channel.mention}",
                    ephemeral=True
                )

                return

        # Trouver la catégorie
        category = discord.utils.get(
            guild.categories,
            name=TICKET_CATEGORY
        )

        if category is None:

            await interaction.response.send_message(
                f"❌ La catégorie `{TICKET_CATEGORY}` n'existe pas.",
                ephemeral=True
            )

            return

        # Permissions
        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            member:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True
                )
        }

        # Rôle staff
        staff_role = discord.utils.get(
            guild.roles,
            name=STAFF_ROLE
        )

        if staff_role:

            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        # Création du ticket
        channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            category=category,
            overwrites=overwrites,
            topic=f"ticket:{member.id}"
        )

        embed = discord.Embed(
            title="🎫 Ticket ouvert",
            description=(
                f"Bienvenue {member.mention} !\n\n"
                "Explique ton problème ou ta demande ici.\n"
                "Un membre du staff viendra te répondre.\n\n"
                "Lorsque ton problème est réglé, utilise le bouton "
                "**Fermer le ticket**."
            ),
            color=discord.Color.blurple()
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


# ==========================================
# FERMETURE DES TICKETS
# ==========================================

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

        if (
            not channel.topic
            or not channel.topic.startswith("ticket:")
        ):

            await interaction.response.send_message(
                "❌ Ce salon n'est pas un ticket.",
                ephemeral=True
            )

            return

        owner_id = int(
            channel.topic.split(":")[1]
        )

        staff_role = discord.utils.get(
            guild.roles,
            name=STAFF_ROLE
        )

        is_owner = interaction.user.id == owner_id

        is_staff = (
            staff_role is not None
            and staff_role in interaction.user.roles
        )

        if not is_owner and not is_staff:

            await interaction.response.send_message(
                "❌ Tu n'as pas la permission de fermer ce ticket.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 Le ticket va être fermé..."
        )

        await channel.delete()


# ==========================================
# CONFIGURATION DU BIENVENUE
# ==========================================

class WelcomeConfigView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.channel_select(
        placeholder="Choisis le salon de bienvenue",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1
    )
    async def select_welcome_channel(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect
    ):

        channel = select.values[0]

        guild_id = str(interaction.guild.id)

        if guild_id not in config:
            config[guild_id] = {}

        config[guild_id]["welcome_channel"] = channel.id

        save_config(config)

        await interaction.response.send_message(
            f"✅ Le salon de bienvenue est maintenant {channel.mention}.",
            ephemeral=True
        )


# ==========================================
# MENU CONFIGURATION
# ==========================================

class ConfigView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="Bienvenue",
        emoji="👋",
        style=discord.ButtonStyle.primary
    )
    async def welcome_config(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        embed = discord.Embed(
            title="👋 Configuration du bienvenue",
            description=(
                "Choisis le salon dans lequel les messages "
                "de bienvenue seront envoyés.\n\n"
                "Utilise le menu ci-dessous pour sélectionner "
                "ton salon."
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            view=WelcomeConfigView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="Tickets",
        emoji="🎫",
        style=discord.ButtonStyle.secondary
    )
    async def tickets_config(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        embed = discord.Embed(
            title="🎫 Configuration des tickets",
            description=(
                f"Le système de tickets utilise actuellement :\n\n"
                f"📁 Catégorie : `{TICKET_CATEGORY}`\n"
                f"📞 Salon : `{TICKET_CHANNEL}`\n"
                f"👮 Rôle staff : `{STAFF_ROLE}`\n\n"
                "La configuration avancée des tickets sera ajoutée "
                "dans une prochaine étape."
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# ==========================================
# COMMANDE /CONFIG
# ==========================================

@bot.tree.command(
    name="config",
    description="Configurer les fonctionnalités du bot"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def config_command(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="⚙️ Configuration",
        description=(
            "**Bienvenue dans le panneau de configuration "
            "de SouthLife Rôle-Play.**\n\n"

            "Sélectionne une fonctionnalité ci-dessous "
            "pour la configurer."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="👋 Bienvenue",
        value="Configure le système de bienvenue.",
        inline=False
    )

    embed.add_field(
        name="🎫 Tickets",
        value="Configure le système de tickets.",
        inline=False
    )

    await interaction.response.send_message(
        embed=embed,
        view=ConfigView(),
        ephemeral=True
    )


# ==========================================
# MESSAGE DE BIENVENUE
# ==========================================

@bot.event
async def on_member_join(
    member: discord.Member
):

    guild_id = str(member.guild.id)

    guild_config = config.get(
        guild_id,
        {}
    )

    channel_id = guild_config.get(
        "welcome_channel"
    )

    if not channel_id:
        print(
            f"ℹ️ Aucun salon de bienvenue configuré pour "
            f"{member.guild.name}"
        )

        return

    channel = member.guild.get_channel(
        channel_id
    )

    if channel is None:
        print(
            "❌ Le salon de bienvenue n'existe plus."
        )

        return

    embed = discord.Embed(
        title="👋 Bienvenue !",
        description=(
            f"Bienvenue {member.mention} sur "
            f"**SouthLife Rôle-Play** !\n\n"

            "Nous sommes heureux de t'accueillir parmi nous. "
            "Prends le temps de lire les règles et de découvrir "
            "le serveur.\n\n"

            "🌴 **Bon jeu à toi !**"
        ),
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.set_footer(
        text=f"Nous sommes maintenant {member.guild.member_count} membres !"
    )

    try:

        await channel.send(
            embed=embed
        )

        print(
            f"👋 Message de bienvenue envoyé pour {member}"
        )

    except discord.Forbidden:

        print(
            "❌ Le bot n'a pas la permission d'envoyer "
            "des messages dans le salon de bienvenue."
        )


# ==========================================
# BOT PRÊT
# ==========================================

@bot.event
async def on_ready():

    print(
        f"✅ Connecté en tant que {bot.user}"
    )

    try:

        synced = await bot.tree.sync()

        print(
            f"✅ {len(synced)} commande(s) synchronisée(s)"
        )

    except Exception as error:

        print(
            f"❌ Erreur de synchronisation : {error}"
        )


# ==========================================
# ENREGISTRER LES BOUTONS PERSISTANTS
# ==========================================

async def setup_hook():

    bot.add_view(
        TicketView()
    )

    bot.add_view(
        CloseTicketView()
    )


bot.setup_hook = setup_hook


# ==========================================
# LANCEMENT
# ==========================================

bot.run(TOKEN)
