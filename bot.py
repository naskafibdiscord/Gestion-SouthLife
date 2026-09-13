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
        "❌ La variable DISCORD_TOKEN n'est pas configurée."
    )


# =========================================================
# FICHIER DE CONFIGURATION
# =========================================================

CONFIG_FILE = "config.json"
MESSAGE_IMAGES_DIR = "message_images"


# Créer le dossier des images s'il n'existe pas
os.makedirs(MESSAGE_IMAGES_DIR, exist_ok=True)


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

# Nécessaire pour détecter les arrivées
intents.members = True


# =========================================================
# BOT
# =========================================================

class MyBot(commands.Bot):

    async def setup_hook(self):

        # Boutons persistants
        self.add_view(TicketView())
        self.add_view(CloseTicketView())


bot = MyBot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# OUTILS
# =========================================================

def split_text(text, limit=2000):
    """
    Découpe un texte en plusieurs morceaux sans dépasser
    la limite Discord des messages classiques.
    """

    if len(text) <= limit:
        return [text]

    chunks = []

    while len(text) > limit:

        # Chercher un retour à la ligne
        cut = text.rfind("\n", 0, limit)

        # Sinon chercher un espace
        if cut == -1:
            cut = text.rfind(" ", 0, limit)

        # Sinon couper directement
        if cut == -1:
            cut = limit

        chunks.append(
            text[:cut].strip()
        )

        text = text[cut:].strip()

    if text:
        chunks.append(text)

    return chunks


def is_image_attachment(attachment: discord.Attachment):

    if not attachment.content_type:
        return False

    return attachment.content_type.startswith("image/")


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

        # Vérifier si l'utilisateur possède déjà un ticket
        for channel in guild.text_channels:

            if channel.topic == f"ticket:{member.id}":

                await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket : {channel.mention}",
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
        staff_role = None

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

        # Créer le ticket
        channel = await guild.create_text_channel(

            name=f"ticket-{member.name}",

            category=category,

            overwrites=overwrites,

            topic=f"ticket:{member.id}"
        )

        # Embed du ticket
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


class TicketCategorySelect(discord.ui.ChannelSelect):

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


class TicketChannelSelect(discord.ui.ChannelSelect):

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


class TicketStaffRoleSelect(discord.ui.RoleSelect):

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


class SaveTicketConfigButton(discord.ui.Button):

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

class WelcomeConfigView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=300)

        self.add_item(
            WelcomeChannelSelect(self)
        )


class WelcomeChannelSelect(discord.ui.ChannelSelect):

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
        interaction: discord.Interaction,
        button: discord.ui.Button
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
        interaction: discord.Interaction,
        button: discord.ui.Button
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
# NOUVEAU : CONFIGURATION DES MESSAGES
# =========================================================

class MessageConfigView(discord.ui.View):

    def __init__(self, guild_id):

        super().__init__(timeout=600)

        self.guild_id = guild_id

        guild_config = config.get(
            str(guild_id),
            {}
        )

        self.channel_id = guild_config.get(
            "message_channel"
        )

        self.message_text = guild_config.get(
            "message_text",
            ""
        )

        self.image_path = guild_config.get(
            "message_image"
        )

        self.add_item(
            MessageChannelSelect(self)
        )

    def get_embed(self):

        text = self.message_text

        if not text:
            text = "Aucun texte configuré."

        # Discord embed description max 4096
        description = text[:4096]

        embed = discord.Embed(
            description=description,
            color=discord.Color.blurple()
        )

        if self.image_path:

            if os.path.exists(
                self.image_path
            ):

                filename = os.path.basename(
                    self.image_path
                )

                embed.set_image(
                    url=f"attachment://{filename}"
                )

        return embed


# =========================================================
# SÉLECTION DU SALON DU MESSAGE
# =========================================================

class MessageChannelSelect(
    discord.ui.ChannelSelect
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            placeholder="📢 Choisir le salon du message",
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

        await interaction.response.edit_message(
            embed=self.parent_view.get_embed(),
            view=self.parent_view
        )

        await interaction.followup.send(
            f"📢 Salon sélectionné : "
            f"{self.values[0].mention}",
            ephemeral=True
        )


# =========================================================
# MODAL TEXTE + IMAGE
# =========================================================

class MessageContentModal(discord.ui.Modal):

    def __init__(self, parent_view):

        super().__init__(
            title="📝 Configurer le message"
        )

        self.parent_view = parent_view

        self.text_input = discord.ui.TextInput(
            label="Texte du message",
            placeholder="Écris ici le message à envoyer...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=4000,
            default=parent_view.message_text[:4000]
        )

        self.image_upload = discord.ui.FileUpload(
            custom_id="message_image_upload",
            required=False,
            min_values=0,
            max_values=1
        )

        self.add_item(
            self.text_input
        )

        self.add_item(
            self.image_upload
        )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        self.parent_view.message_text = (
            self.text_input.value
        )

        # Vérifier l'image
        if self.image_upload.values:

            attachment = (
                self.image_upload.values[0]
            )

            if not is_image_attachment(
                attachment
            ):

                await interaction.response.send_message(
                    "❌ Le fichier sélectionné n'est "
                    "pas une image.",
                    ephemeral=True
                )

                return

            try:

                data = await attachment.read()

                extension = (
                    os.path.splitext(
                        attachment.filename
                    )[1]
                    or ".png"
                )

                guild_id = str(
                    interaction.guild.id
                )

                filename = (
                    f"message_{guild_id}"
                    f"{extension}"
                )

                path = os.path.join(
                    MESSAGE_IMAGES_DIR,
                    filename
                )

                # Supprimer une ancienne image
                old_path = (
                    self.parent_view.image_path
                )

                if (
                    old_path
                    and old_path != path
                    and os.path.exists(old_path)
                ):

                    try:
                        os.remove(old_path)
                    except OSError:
                        pass

                with open(
                    path,
                    "wb"
                ) as file:

                    file.write(data)

                self.parent_view.image_path = path

            except Exception as error:

                print(
                    f"❌ Erreur sauvegarde image : {error}"
                )

                await interaction.response.send_message(
                    "❌ Impossible d'enregistrer l'image.",
                    ephemeral=True
                )

                return

        # Enregistrer automatiquement
        guild_id = str(
            interaction.guild.id
        )

        if guild_id not in config:
            config[guild_id] = {}

        config[guild_id][
            "message_text"
        ] = self.parent_view.message_text

        config[guild_id][
            "message_image"
        ] = self.parent_view.image_path

        if self.parent_view.channel_id:

            config[guild_id][
                "message_channel"
            ] = self.parent_view.channel_id

        save_config(config)

        await interaction.response.edit_message(
            embed=self.parent_view.get_embed(),
            view=self.parent_view
        )

        await interaction.followup.send(
            "✅ Le texte et l'image ont été enregistrés.",
            ephemeral=True
        )


# =========================================================
# BOUTON MODIFIER MESSAGE
# =========================================================

class EditMessageButton(
    discord.ui.Button
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            label="Modifier le message",
            emoji="📝",
            style=discord.ButtonStyle.primary
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.send_modal(
            MessageContentModal(
                self.parent_view
            )
        )


# =========================================================
# BOUTON SUPPRIMER IMAGE
# =========================================================

class RemoveMessageImageButton(
    discord.ui.Button
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            label="Supprimer l'image",
            emoji="🗑️",
            style=discord.ButtonStyle.danger
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        path = self.parent_view.image_path

        if path and os.path.exists(path):

            try:
                os.remove(path)
            except OSError:
                pass

        self.parent_view.image_path = None

        guild_id = str(
            interaction.guild.id
        )

        if guild_id in config:

            config[guild_id][
                "message_image"
            ] = None

            save_config(config)

        await interaction.response.edit_message(
            embed=self.parent_view.get_embed(),
            view=self.parent_view
        )

        await interaction.followup.send(
            "🗑️ Image supprimée.",
            ephemeral=True
        )


# =========================================================
# APERÇU
# =========================================================

class MessagePreviewButton(
    discord.ui.Button
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            label="Aperçu",
            emoji="👀",
            style=discord.ButtonStyle.secondary
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        embed = self.parent_view.get_embed()

        files = []

        if self.parent_view.image_path:

            path = self.parent_view.image_path

            if os.path.exists(path):

                files.append(
                    discord.File(
                        path,
                        filename=os.path.basename(path)
                    )
                )

        await interaction.response.send_message(
            content="👀 **Aperçu du message :**",
            embed=embed,
            files=files,
            ephemeral=True
        )


# =========================================================
# ENVOYER LE MESSAGE
# =========================================================

class SendConfiguredMessageButton(
    discord.ui.Button
):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        super().__init__(
            label="Envoyer",
            emoji="📤",
            style=discord.ButtonStyle.success
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        view = self.parent_view

        if view.channel_id is None:

            await interaction.response.send_message(
                "❌ Tu dois choisir un salon.",
                ephemeral=True
            )

            return

        if not view.message_text:

            await interaction.response.send_message(
                "❌ Tu dois écrire un message.",
                ephemeral=True
            )

            return

        channel = interaction.guild.get_channel(
            view.channel_id
        )

        if channel is None:

            await interaction.response.send_message(
                "❌ Le salon sélectionné n'existe plus.",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        text = view.message_text

        # -------------------------------------------------
        # IMAGE
        # -------------------------------------------------

        image_file = None

        if view.image_path:

            if os.path.exists(
                view.image_path
            ):

                image_file = discord.File(
                    view.image_path,
                    filename=os.path.basename(
                        view.image_path
                    )
                )

        # -------------------------------------------------
        # TEXTE <= 4096
        # -------------------------------------------------

        if len(text) <= 4096:

            embed = discord.Embed(
                description=text,
                color=discord.Color.blurple()
            )

            if image_file:

                embed.set_image(
                    url=(
                        "attachment://"
                        + os.path.basename(
                            view.image_path
                        )
                    )
                )

            await channel.send(
                embed=embed,
                file=image_file
            )

        # -------------------------------------------------
        # TEXTE LONG
        # -------------------------------------------------

        else:

            chunks = split_text(
                text,
                2000
            )

            for index, chunk in enumerate(chunks):

                # Mettre l'image sur le premier message
                if index == 0:

                    embed = discord.Embed(
                        description=chunk,
                        color=discord.Color.blurple()
                    )

                    if image_file:

                        embed.set_image(
                            url=(
                                "attachment://"
                                + os.path.basename(
                                    view.image_path
                                )
                            )
                        )

                    await channel.send(
                        embed=embed,
                        file=image_file
                    )

                else:

                    await channel.send(
                        chunk
                    )

        # Sauvegarder
        guild_id = str(
            interaction.guild.id
        )

        if guild_id not in config:
            config[guild_id] = {}

        config[guild_id][
            "message_channel"
        ] = view.channel_id

        config[guild_id][
            "message_text"
        ] = view.message_text

        config[guild_id][
            "message_image"
        ] = view.image_path

        save_config(config)

        await interaction.followup.send(
            f"✅ Message envoyé dans {channel.mention} !",
            ephemeral=True
        )


# =========================================================
# VIEW PRINCIPALE CONFIG MESSAGE
# =========================================================

class MessageConfigButtonsView(
    MessageConfigView
):

    def __init__(self, guild_id):

        super().__init__(
            guild_id
        )

        self.add_item(
            EditMessageButton(self)
        )

        self.add_item(
            MessagePreviewButton(self)
        )

        self.add_item(
            SendConfiguredMessageButton(self)
        )

        self.add_item(
            RemoveMessageImageButton(self)
        )


# =========================================================
# /CONFIGMS
# =========================================================

@bot.tree.command(
    name="configms",
    description="Configurer et envoyer un message personnalisé"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def configms_command(
    interaction: discord.Interaction
):

    guild = interaction.guild

    if guild is None:

        await interaction.response.send_message(
            "❌ Cette commande doit être utilisée "
            "dans un serveur.",
            ephemeral=True
        )

        return

    view = MessageConfigButtonsView(
        guild.id
    )

    embed = discord.Embed(

        title="📨 Configuration du message",

        description=(
            "Configure ici ton message personnalisé.\n\n"

            "📢 **Salon**\n"
            "Choisis le salon dans lequel le message "
            "sera envoyé.\n\n"

            "📝 **Message**\n"
            "Clique sur **📝 Modifier le message** "
            "pour écrire ton texte.\n\n"

            "🖼️ **Image**\n"
            "Dans la même fenêtre, tu peux sélectionner "
            "une image depuis ta galerie/fichiers.\n\n"

            "👀 **Aperçu**\n"
            "Permet de voir exactement le rendu avant "
            "de l'envoyer.\n\n"

            "📤 **Envoyer**\n"
            "Envoie définitivement le message dans "
            "le salon sélectionné."
        ),

        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )


@configms_command.error
async def configms_command_error(
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
            f"❌ Erreur /configms : {error}"
        )

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "❌ Une erreur est survenue.",
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
            "**Bienvenue dans le panneau de "
            "configuration de SouthLife Rôle-Play.**\n\n"

            "Sélectionne une fonctionnalité "
            "ci-dessous pour la configurer."
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

    guild_id = str(
        guild.id
    )

    guild_config = config.get(
        guild_id,
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

            'Bienvenue dans l\'onglet "besoin d\'aide" '
            "de SouthLife Rôle-Play.\n\n"

            "Si vous avez besoin d'aide vous êtes au "
            "bon endroit ! Cependant si votre aide ne "
            "nécessite pas forcément un ticket Discord, "
            "faites un report en jeu et attendez un staff.\n\n"

            "Lorsque vous créez un ticket merci d'être "
            "le plus précis possible dans votre démarche.\n\n"

            "Cela facilitera la compréhension du staff "
            "et la rapidité de résolution de votre demande.\n\n"

            "À noter que nous sommes des humains, pas "
            "des robots. Merci donc de patienter sagement "
            "qu'un staff vous réponde.\n\n"

            "(Les pings abusifs seront sanctionnés.)\n\n"

            "De plus la politesse ne fait pas de mal, "
            "un bonjour ou un merci est bienvenu.\n\n"

            "En espérant pouvoir régler tous vos soucis."
        ),

        color=discord.Color.blurple()
    )

    embed.set_footer(
        text=(
            "Système de tickets • "
            "SouthLife Rôle-Play"
        )
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
# BIENVENUE + RÔLE CIVILS
# =========================================================

@bot.event
async def on_member_join(
    member: discord.Member
):

    guild = member.guild

    # -----------------------------------------------------
    # DONNER LE RÔLE ・Civils
    # -----------------------------------------------------

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
                reason=(
                    "Attribution automatique "
                    "du rôle à l'arrivée"
                )
            )

            print(
                f"👤 Rôle ・Civils donné à "
                f"{member}"
            )

        except discord.Forbidden:

            print(
                "❌ Impossible de donner le rôle "
                "・Civils."
            )

            print(
                "Vérifie que le rôle du bot est "
                "au-dessus du rôle ・Civils."
            )

        except Exception as error:

            print(
                f"❌ Erreur attribution rôle : "
                f"{error}"
            )

    # -----------------------------------------------------
    # RÉCUPÉRER CONFIG BIENVENUE
    # -----------------------------------------------------

    guild_id = str(
        guild.id
    )

    guild_config = config.get(
        guild_id,
        {}
    )

    welcome_channel_id = guild_config.get(
        "welcome_channel"
    )

    if not welcome_channel_id:

        print(
            f"ℹ️ Aucun salon de bienvenue "
            f"configuré pour {guild.name}"
        )

        return

    channel = guild.get_channel(
        welcome_channel_id
    )

    if channel is None:

        print(
            "❌ Le salon de bienvenue "
            "n'existe plus."
        )

        return

    # -----------------------------------------------------
    # MESSAGE DE BIENVENUE
    # -----------------------------------------------------

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
            f"👋 Message de bienvenue envoyé "
            f"pour {member}"
        )

    except discord.Forbidden:

        print(
            "❌ Le bot n'a pas la permission "
            "d'envoyer des messages dans "
            "le salon de bienvenue."
        )


# =========================================================
# BOT PRÊT
# =========================================================

@bot.event
async def on_ready():

    print(
        f"✅ Connecté en tant que "
        f"{bot.user}"
    )

    try:

        synced = await bot.tree.sync()

        print(
            f"✅ {len(synced)} commande(s) synchronisée(s)"
        )

    except Exception as error:

        print(
            f"❌ Erreur de synchronisation : "
            f"{error}"
        )


# =========================================================
# LANCEMENT
# =========================================================

bot.run(TOKEN)
