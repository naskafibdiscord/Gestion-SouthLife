import os
import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")

# Configuration
TICKET_CATEGORY = "🎫-tickets"
TICKET_CHANNEL = "📞丨contact"
STAFF_ROLE = "Staff"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# BOUTON OUVRIR UN TICKET
# =========================

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

        # Vérifier si la personne possède déjà un ticket
        for channel in guild.text_channels:
            if channel.topic == f"ticket:{member.id}":
                await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket : {channel.mention}",
                    ephemeral=True
                )
                return

        # Chercher la catégorie
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

        # Permissions du ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),

            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        }

        # Rôle Staff
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

        # Créer le ticket
        channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            category=category,
            overwrites=overwrites,
            topic=f"ticket:{member.id}"
        )

        # Message dans le ticket
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


# =========================
# BOUTON FERMER UN TICKET
# =========================

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

        # Vérifier que c'est un ticket
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

        # Chercher le rôle Staff
        staff_role = discord.utils.get(
            guild.roles,
            name=STAFF_ROLE
        )

        is_owner = interaction.user.id == owner_id

        is_staff = (
            staff_role is not None
            and staff_role in interaction.user.roles
        )

        # Vérifier les permissions
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
        

# =========================
# SYSTÈME DE BIENVENUE
# =========================

WELCOME_CHANNEL = "👋丨bienvenue"


@bot.event
async def on_member_join(member: discord.Member):

    channel = discord.utils.get(
        member.guild.text_channels,
        name=WELCOME_CHANNEL
    )

    if channel is None:
        print(
            f"❌ Le salon {WELCOME_CHANNEL} n'existe pas."
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
        text=f"Membre #{member.guild.member_count}"
    )

    await channel.send(
        embed=embed
    )
# =========================
# BOT PRÊT
# =========================

@bot.event
async def on_ready():

    print(f"✅ Connecté en tant que {bot.user}")

    # Boutons persistants
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())

    # Synchronisation des commandes
    try:
        synced = await bot.tree.sync()

        print(
            f"✅ {len(synced)} commande(s) synchronisée(s)"
        )

    except Exception as error:

        print(
            f"❌ Erreur de synchronisation : {error}"
        )


# =========================
# COMMANDE /TICKETPANEL
# =========================

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

    # Chercher le salon contact
    channel = discord.utils.get(
        interaction.guild.text_channels,
        name=TICKET_CHANNEL
    )

    if channel is None:

        await interaction.response.send_message(
            f"❌ Le salon `{TICKET_CHANNEL}` n'existe pas.",
            ephemeral=True
        )

        return

    # =========================
    # TON MESSAGE PERSONNALISÉ
    # =========================

    embed = discord.Embed(
        title="Tickets",
        description=(
            'Bienvenue dans l\'onglet "besoin d\'aide" '
            'de SouthLife Rôle-Play.\n\n'

            "Si vous avez besoin d'aide vous êtes au bon endroit ! "
            "Cependant si votre aide ne nécessite pas forcément un "
            "ticket Discord, faites un report en jeu et attendez un staff.\n\n"

            "Lorsque vous créez un ticket merci d'être le plus précis "
            "possible dans votre démarche.\n\n"

            "Cela facilitera la compréhension du staff et la rapidité "
            "de résolution de votre demande.\n\n"

            "À noter que nous sommes des humains, pas des robots. "
            "Merci donc de patienter sagement qu'un staff vous réponde "
            "(Les pings abusifs seront sanctionnés). "

            "De plus la politesse ne fait pas de mal, "
            "un bonjour ou un merci est bienvenu.\n\n"

            "En espérant pouvoir régler tous vos soucis."
        ),
        color=discord.Color.blurple()
    )
    embed.set_image(
    url="https://cdn.discordapp.com/attachments/1547338843198324772/1548350157475676241/9B8AD993-6D75-476A-8C61-946178416A45.png?ex=6aa6bcf4&is=6aa56b74&hm=3bac0b652af3970707ea6272b949031c2fefb255b720fdf9f8f49f877b07fd36&"
)

    embed.set_footer(
        text="Système de tickets"
    )

    # Envoyer le panneau
    await channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "✅ Le panneau de tickets a été créé !",
        ephemeral=True
    )


# =========================
# GESTION DES ERREURS
# =========================

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
            "❌ Tu dois être administrateur pour utiliser cette commande.",
            ephemeral=True
        )

    else:

        await interaction.response.send_message(
            "❌ Une erreur est survenue.",
            ephemeral=True
        )


# =========================
# LANCEMENT DU BOT
# =========================

bot.run(TOKEN)
