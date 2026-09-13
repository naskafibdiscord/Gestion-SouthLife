import os
import json
import discord
from discord.ext import commands
from discord import app_commands


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError(
        "La variable DISCORD_TOKEN n'est pas configuree."
    )


# =========================================================
# CONFIGURATION
# =========================================================

CONFIG_FILE = "config.json"

REGLEMENT_IMAGE_URL = (
    "https://cdn.discordapp.com/attachments/"
    "1547338843198324772/1548644935203561552/image.jpg"
    "?ex=6aa7cf7c&is=6aa67dfc"
    "&hm=2d4be46fb29c02b579285d43946c999799addad87f615b93a3376c665857da12&"
)

REGLEMENT_CHANNEL_NAME = "📋丨règlement"
REGLEMENT_ROLE_NAME = "🐬・Alya RP - Règlement"


# =========================================================
# CHARGEMENT CONFIGURATION
# =========================================================

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )


config = load_config()


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.members = True


# =========================================================
# BOT
# =========================================================

class MyBot(commands.Bot):

    async def setup_hook(self):

        # Vues persistantes
        self.add_view(TicketView())
        self.add_view(CloseTicketView())
        self.add_view(ReglementView())


bot = MyBot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# SYSTÈME DE TICKETS
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

        if guild is None:
            return

        guild_config = config.get(
            str(guild.id),
            {}
        )

        category_id = guild_config.get(
            "ticket_category"
        )

        staff_role_id = guild_config.get(
            "ticket_staff_role"
        )

        if not category_id:

            await interaction.response.send_message(
                "❌ Le système de tickets n'est pas configuré.\n\n"
                "Un administrateur doit utiliser `/config` "
                "puis **🎫 Tickets**.",
                ephemeral=True
            )

            return

        category = guild.get_channel(
            category_id
        )

        if category is None:

            await interaction.response.send_message(
                "❌ La catégorie configurée n'existe plus.\n\n"
                "Utilise `/config` pour la reconfigurer.",
                ephemeral=True
            )

            return

        # Vérification ticket déjà existant
        for channel in guild.text_channels:

            if channel.topic == f"ticket:{member.id}":

                await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket : {channel.mention}",
                    ephemeral=True
                )

                return

        # Permissions du ticket
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

        # Permissions du staff
        if staff_role_id:

            staff_role = guild.get_role(
                staff_role_id
            )

            if staff_role:

                overwrites[staff_role] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True
                    )
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
                "Lorsque ton problème est réglé, "
                "utilise le bouton **🔒 Fermer le ticket**."
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


# =========================================================
# FERMER UN TICKET
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

        if channel is None or guild is None:
            return

        if (
            not channel.topic
            or not channel.topic.startswith("ticket:")
        ):

            await interaction.response.send_message(
                "❌ Ce salon n'est pas un ticket.",
                ephemeral=True
            )

            return

        try:

            owner_id = int(
                channel.topic.split(":")[1]
            )

        except (ValueError, IndexError):

            await interaction.response.send_message(
                "❌ Impossible de déterminer "
                "le propriétaire du ticket.",
                ephemeral=True
            )

            return

        guild_config = config.get(
            str(guild.id),
            {}
        )

        staff_role_id = guild_config.get(
            "ticket_staff_role"
        )

        staff_role = None

        if staff_role_id:

            staff_role = guild.get_role(
                staff_role_id
            )

        is_owner = (
            interaction.user.id == owner_id
        )

        is_staff = (
            staff_role is not None
            and staff_role in interaction.user.roles
        )

        if not is_owner and not is_staff:

            await interaction.response.send_message(
                "❌ Tu n'as pas la permission "
                "de fermer ce ticket.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 Le ticket va être fermé..."
        )

        await channel.delete()


# =========================================================
# CONFIGURATION DES TICKETS
# =========================================================

class TicketConfigView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=300)

        self.category_id = None
        self.channel_id = None
        self.staff_role_id = None

        self.add_item(
            TicketCategorySelect(self)
        )

        self.add_item(
            TicketChannelSelect(self)
        )

        self.add_item(
            TicketStaffRoleSelect(self)
        )

        self.add_item(
            SaveTicketConfigButton(self)
        )


class TicketCategorySelect(
    discord.ui.ChannelSelect
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            placeholder="📁 Choisir la catégorie des tickets",
            channel_types=[
                discord.ChannelType.category
            ],
            min_values=1,
            max_values=1
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        self.parent_view.category_id = (
            self.values[0].id
        )

        await interaction.response.send_message(
            f"📁 Catégorie sélectionnée : "
            f"**{self.values[0].name}**",
            ephemeral=True
        )


class TicketChannelSelect(
    discord.ui.ChannelSelect
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            placeholder="📞 Choisir le salon du panneau",
            channel_types=[
                discord.ChannelType.text
            ],
            min_values=1,
            max_values=1
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        self.parent_view.channel_id = (
            self.values[0].id
        )

        await interaction.response.send_message(
            f"📞 Salon sélectionné : "
            f"{self.values[0].mention}",
            ephemeral=True
        )


class TicketStaffRoleSelect(
    discord.ui.RoleSelect
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            placeholder="👮 Choisir le rôle du staff",
            min_values=1,
            max_values=1
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        self.parent_view.staff_role_id = (
            self.values[0].id
        )

        await interaction.response.send_message(
            f"👮 Rôle sélectionné : "
            f"{self.values[0].mention}",
            ephemeral=True
        )


class SaveTicketConfigButton(
    discord.ui.Button
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            label="Enregistrer",
            emoji="💾",
            style=discord.ButtonStyle.green
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        view = self.parent_view

        if view.category_id is None:

            await interaction.response.send_message(
                "❌ Tu dois choisir une catégorie.",
                ephemeral=True
            )

            return

        if view.channel_id is None:

            await interaction.response.send_message(
                "❌ Tu dois choisir le salon du panneau.",
                ephemeral=True
            )

            return

        if view.staff_role_id is None:

            await interaction.response.send_message(
                "❌ Tu dois choisir le rôle du staff.",
                ephemeral=True
            )

            return

        guild_id = str(
            interaction.guild.id
        )

        if guild_id not in config:
            config[guild_id] = {}

        config[guild_id][
            "ticket_category"
        ] = view.category_id

        config[guild_id][
            "ticket_channel"
        ] = view.channel_id

        config[guild_id][
            "ticket_staff_role"
        ] = view.staff_role_id

        save_config(config)

        await interaction.response.send_message(
            "✅ **Configuration des tickets enregistrée !**\n\n"
            f"📁 Catégorie : <#{view.category_id}>\n"
            f"📞 Salon : <#{view.channel_id}>\n"
            f"👮 Rôle staff : <@&{view.staff_role_id}>",
            ephemeral=True
        )


# =========================================================
# CONFIGURATION BIENVENUE
# =========================================================

class WelcomeConfigView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=300)

        self.add_item(
            WelcomeChannelSelect(self)
        )


class WelcomeChannelSelect(
    discord.ui.ChannelSelect
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            placeholder="👋 Choisir le salon de bienvenue",
            channel_types=[
                discord.ChannelType.text
            ],
            min_values=1,
            max_values=1
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        channel = self.values[0]

        guild_id = str(
            interaction.guild.id
        )

        if guild_id not in config:
            config[guild_id] = {}

        config[guild_id][
            "welcome_channel"
        ] = channel.id

        save_config(config)

        await interaction.response.send_message(
            f"✅ Le salon de bienvenue est maintenant "
            f"{channel.mention}.",
            ephemeral=True
        )


# =========================================================
# MENU /CONFIG
# =========================================================

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
        interaction,
        button
    ):

        embed = discord.Embed(
            title="👋 Configuration du bienvenue",
            description=(
                "Configure ici ton système de bienvenue.\n\n"
                "Sélectionne le salon dans lequel "
                "les messages de bienvenue seront envoyés."
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
        interaction,
        button
    ):

        embed = discord.Embed(
            title="🎫 Configuration des tickets",
            description=(
                "Configure ici ton système de tickets.\n\n"
                "📁 **Catégorie**\n"
                "Les tickets seront créés dans cette catégorie.\n\n"
                "📞 **Salon du panneau**\n"
                "Le panneau `/ticketpanel` sera envoyé "
                "dans ce salon.\n\n"
                "👮 **Rôle staff**\n"
                "Ce rôle pourra accéder aux tickets.\n\n"
                "Sélectionne les éléments ci-dessous "
                "puis appuie sur **💾 Enregistrer**."
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            view=TicketConfigView(),
            ephemeral=True
        )


# =========================================================
# SYSTÈME DE RÈGLEMENT
# =========================================================

class ReglementView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="J'accepte le règlement",
        emoji="✅",
        style=discord.ButtonStyle.green,
        custom_id="accept_reglement"
    )
    async def accept_reglement(
        self,
        interaction,
        button
    ):

        guild = interaction.guild
        member = interaction.user

        if guild is None:
            return

        role = discord.utils.get(
            guild.roles,
            name=REGLEMENT_ROLE_NAME
        )

        if role is None:

            await interaction.response.send_message(
                f"❌ Le rôle **{REGLEMENT_ROLE_NAME}** "
                "n'existe pas sur le serveur.",
                ephemeral=True
            )

            return

        if role in member.roles:

            await interaction.response.send_message(
                "✅ Tu as déjà accepté le règlement.",
                ephemeral=True
            )

            return

        if guild.me is None:

            await interaction.response.send_message(
                "❌ Impossible de vérifier les permissions du bot.",
                ephemeral=True
            )

            return

        if role >= guild.me.top_role:

            await interaction.response.send_message(
                "❌ Je ne peux pas donner ce rôle.\n\n"
                "Place le rôle du règlement **sous le rôle "
                "du bot** dans les paramètres du serveur.",
                ephemeral=True
            )

            return

        try:

            await member.add_roles(
                role,
                reason="Acceptation du règlement"
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ Je n'ai pas la permission de donner ce rôle.\n\n"
                "Vérifie que le rôle du bot est au-dessus "
                "du rôle du règlement.",
                ephemeral=True
            )

            return

        except Exception as error:

            print(
                f"❌ Erreur attribution rôle règlement : {error}"
            )

            await interaction.response.send_message(
                "❌ Une erreur est survenue lors de "
                "l'attribution du rôle.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            f"✅ **Règlement accepté !**\n\n"
            f"Le rôle {role.mention} t'a été attribué.",
            ephemeral=True
        )


# =========================================================
# EMBED DU RÈGLEMENT
# =========================================================

def create_reglement_embed():

    description = (
        "**Règlement des Serveurs**\n"
        "**Discord SouthLife RP**\n\n"

        "**1 -** Soyez respectueux avec tout le monde.\n\n"

        "**2 -** Nous respectons les conditions "
        "d'utilisation de Discord. Vous devez avoir "
        "13 ans ou plus pour utiliser les services Discord.\n\n"

        "**3 -** Ne spammez pas de texte, d'emotes ou "
        "d'images dans les salons textuels.\n\n"

        "**4 -** N'indiquez pas de messages de type "
        "NSFW / Pub / propos haineux dans le chat ou "
        "dans des statuts personnalisés.\n\n"

        "**5 -** Il s'agit d'un serveur francophone. "
        "Veuillez ne pas communiquer dans d'autres langues. "
        "C'est ainsi que nous pouvons modérer pleinement.\n\n"

        "**6 -** Interdiction de ping un staff pour "
        "n'importe quelle raison.\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n\n"

        "Nous respectons les **T.O.S.**\n"
        "(*Terms of Service*) appliqués par Discord.\n\n"

        "Toutes les règles ci-dessus sont passibles "
        "de sanctions, ne venez pas vous plaindre !"
    )

    embed = discord.Embed(
        title="📋 Règlement des Serveurs",
        description=description,
        color=discord.Color.blurple()
    )

    if REGLEMENT_IMAGE_URL:
        embed.set_image(
            url=REGLEMENT_IMAGE_URL
        )

    embed.set_footer(
        text="Discord Alya RP • Merci de respecter le règlement."
    )

    return embed


# =========================================================
# /REGLEMENT
# =========================================================

@bot.tree.command(
    name="reglement",
    description="Envoyer le règlement du serveur"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def reglement_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:

        await interaction.response.send_message(
            "❌ Cette commande doit être utilisée "
            "sur un serveur.",
            ephemeral=True
        )

        return

    channel = discord.utils.get(
        guild.text_channels,
        name=REGLEMENT_CHANNEL_NAME
    )

    if channel is None:

        await interaction.response.send_message(
            f"❌ Je ne trouve pas le salon "
            f"`{REGLEMENT_CHANNEL_NAME}`.\n\n"
            "Vérifie que le salon existe et que "
            "son nom est exactement le même.",
            ephemeral=True
        )

        return

    try:

        await channel.send(
            embed=create_reglement_embed(),
            view=ReglementView()
        )

    except discord.Forbidden:

        await interaction.response.send_message(
            f"❌ Je n'ai pas la permission d'envoyer "
            f"des messages dans {channel.mention}.",
            ephemeral=True
        )

        return

    except Exception as error:

        print(
            f"❌ Erreur envoi règlement : {error}"
        )

        await interaction.response.send_message(
            "❌ Une erreur est survenue lors de "
            "l'envoi du règlement.",
            ephemeral=True
        )

        return

    await interaction.response.send_message(
        f"✅ Le règlement a été envoyé dans "
        f"{channel.mention} !",
        ephemeral=True
    )


# =========================================================
# /CONFIG
# =========================================================

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
        value=(
            "Configure le système de bienvenue "
            "et l'attribution du rôle."
        ),
        inline=False
    )

    embed.add_field(
        name="🎫 Tickets",
        value=(
            "Configure le système de tickets."
        ),
        inline=False
    )

    await interaction.response.send_message(
        embed=embed,
        view=ConfigView(),
        ephemeral=True
    )


# =========================================================
# /TICKETPANEL
# =========================================================

@bot.tree.command(
    name="ticketpanel",
    description="Créer le panneau pour ouvrir des tickets"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def ticketpanel(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:
        return

    guild_config = config.get(
        str(guild.id),
        {}
    )

    channel_id = guild_config.get(
        "ticket_channel"
    )

    if not channel_id:

        await interaction.response.send_message(
            "❌ Le système de tickets n'est pas configuré.\n\n"
            "Utilise `/config` → **🎫 Tickets** "
            "pour le configurer.",
            ephemeral=True
        )

        return

    channel = guild.get_channel(
        channel_id
    )

    if channel is None:

        await interaction.response.send_message(
            "❌ Le salon configuré n'existe plus.\n\n"
            "Utilise `/config` → **🎫 Tickets** "
            "pour choisir un nouveau salon.",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title="Tickets",
        description=(
            "Bienvenue dans l'onglet "
            "\"besoin d'aide\" de SouthLife Rôle-Play.\n\n"

            "Si vous avez besoin d'aide, vous êtes au "
            "bon endroit ! Cependant, si votre demande "
            "ne nécessite pas forcément un ticket Discord, "
            "faites un report en jeu et attendez un staff.\n\n"

            "Lorsque vous créez un ticket, merci d'être "
            "le plus précis possible dans votre démarche.\n\n"

            "Cela facilitera la compréhension du staff "
            "et la rapidité de résolution de votre demande.\n\n"

            "À noter que nous sommes des humains, pas "
            "des robots. Merci donc de patienter "
            "sagement qu'un staff vous réponde.\n\n"

            "(Les pings abusifs seront sanctionnés.)\n\n"

            "De plus, la politesse ne fait pas de mal : "
            "un bonjour ou un merci est bienvenu.\n\n"

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
        f"✅ Le panneau de tickets a été envoyé "
        f"dans {channel.mention} !",
        ephemeral=True
    )


# =========================================================
# BIENVENUE + RÔLE CIVILS
# =========================================================

@bot.event
async def on_member_join(
    member: discord.Member
):

    guild = member.guild

    # Rôle Civils
    civils_role = discord.utils.get(
        guild.roles,
        name="・Civils"
    )

    if civils_role is None:

        print(
            "❌ Le rôle ・Civils n'existe pas."
        )

    else:

        try:

            await member.add_roles(
                civils_role,
                reason="Attribution automatique du rôle à l'arrivée"
            )

            print(
                f"👤 Rôle ・Civils donné à {member}"
            )

        except discord.Forbidden:

            print(
                "❌ Impossible de donner le rôle ・Civils."
            )

            print(
                "Vérifie que le rôle du bot est au-dessus "
                "du rôle ・Civils."
            )

        except Exception as error:

            print(
                f"❌ Erreur attribution rôle : {error}"
            )

    # Message de bienvenue
    guild_config = config.get(
        str(guild.id),
        {}
    )

    welcome_channel_id = guild_config.get(
        "welcome_channel"
    )

    if not welcome_channel_id:

        print(
            f"ℹ️ Aucun salon de bienvenue configuré "
            f"pour {guild.name}"
        )

        return

    channel = guild.get_channel(
        welcome_channel_id
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
            "Nous sommes heureux de t'accueillir "
            "parmi nous.\n\n"
            "🌴 **Bon jeu à toi !**"
        ),
        color=discord.Color.blurple()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.set_footer(
        text=(
            f"Nous sommes maintenant "
            f"{guild.member_count} membres !"
        )
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


# =========================================================
# ERREURS /CONFIG
# =========================================================

@config_command.error
async def config_command_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        await interaction.response.send_message(
            "❌ Tu dois être administrateur "
            "pour utiliser cette commande.",
            ephemeral=True
        )

    else:

        print(
            f"❌ Erreur /config : {error}"
        )

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "❌ Une erreur est survenue.",
                ephemeral=True
            )


# =========================================================
# ERREURS /TICKETPANEL
# =========================================================

@ticketpanel.error
async def ticketpanel_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        await interaction.response.send_message(
            "❌ Tu dois être administrateur "
            "pour utiliser cette commande.",
            ephemeral=True
        )

    else:

        print(
            f"❌ Erreur /ticketpanel : {error}"
        )

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "❌ Une erreur est survenue.",
                ephemeral=True
            )


# =========================================================
# ERREURS /REGLEMENT
# =========================================================

@reglement_command.error
async def reglement_command_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        await interaction.response.send_message(
            "❌ Tu dois être administrateur "
            "pour utiliser cette commande.",
            ephemeral=True
        )

    else:

        print(
            f"❌ Erreur /reglement : {error}"
        )

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "❌ Une erreur est survenue.",
                ephemeral=True
            )


# =========================================================
# BOT PRÊT
# =========================================================

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


# =========================================================
# LANCEMENT
# =========================================================

bot.run(TOKEN)
