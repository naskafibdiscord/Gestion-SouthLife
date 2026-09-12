import os
import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")

# Noms utilisés sur ton serveur
TICKET_CATEGORY = "🎫 TICKETS"
TICKET_CHANNEL = "🎫・ouvrir-un-ticket"
STAFF_ROLE = "Staff"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


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

        # Permissions du nouveau salon
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

        # Ajouter le rôle Staff s'il existe
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

        # Vérifier que c'est bien un ticket
        if not channel.topic or not channel.topic.startswith("ticket:"):
            await interaction.response.send_message(
                "❌ Ce salon n'est pas un ticket.",
                ephemeral=True
            )
            return

        owner_id = int(channel.topic.split(":")[1])

        staff_role = discord.utils.get(
            guild.roles,
            name=STAFF_ROLE
        )

        is_owner = interaction.user.id == owner_id
        is_staff = staff_role and staff_role in interaction.user.roles

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


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")

    # Enregistrer les boutons persistants
    bot.add_view(TicketView())
    bot.add_view(CloseTicketView())

    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commande(s) synchronisée(s)")
    except Exception as error:
        print(f"❌ Erreur de synchronisation : {error}")


@bot.tree.command(
    name="ticketpanel",
    description="Créer le panneau pour ouvrir des tickets"
)
@app_commands.checks.has_permissions(administrator=True)
async def ticketpanel(interaction: discord.Interaction):

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

    embed = discord.Embed(
        title="🎫 Support",
        description=(
            "Besoin d'aide ?\n\n"
            "Clique sur le bouton ci-dessous pour créer un ticket.\n\n"
            "Un salon privé sera automatiquement créé "
            "pour toi et le staff."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="Système de tickets"
    )

    await channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "✅ Le panneau de tickets a été créé !",
        ephemeral=True
    )


@ticketpanel.error
async def ticketpanel_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "❌ Tu dois être administrateur pour utiliser cette commande.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ Une erreur est survenue.",
            ephemeral=True
        )


bot.run(TOKEN)
