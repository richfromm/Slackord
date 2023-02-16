import logging
from typing import cast, Optional, Union

import discord


logger = logging.getLogger(__name__)

# the maximum number of Embed's that can be included when sending to Discord
# specified at:
# https://discordpy.readthedocs.io/en/latest/api.html#discord.TextChannel.send
# https://discordpy.readthedocs.io/en/latest/api.html#discord.Thread.send
MAX_DISCORD_EMBEDS = 10


class ParsedMessage():
    """
    A single message that has been parsed from a Slack export.

    This is in a format to be convenient to post to Discord.  But it is not necessarily precisely
    either a Slack message, or a Discord message. It is in whatever intermediate format works for
    this process. Fields tend to be more based on Slack naming conventions, but not precisely, and
    contents may be modified and/or combined. See SlackParser.parse_message() for more details.
    """
    def __init__(self, text: str) -> None:
        self.text = text
        self.links: list[MessageLink] = []
        self.files: list[MessageFile] = []

    @staticmethod
    def str_or_none(val: Optional[str]) -> str:
        """
        Return a string of a value suitable for a string representation of the form:
           key='value'
        The point is that we **do** want the quotes if it's really a string,
        but we do **not** want the quotes if the value is None.

        Used with MessageLink and MessageFile
        """
        if val is None:
            return f"{val}"

        return f"'{val}'"

    def add_link(self, link_dict: dict[str, str]) -> None:
        """
        Add the info for a link to the parsed message

        This is stored internally as self.links, which is a list of MessageLink
        Slack calls links 'attachments', Discord calls them Embed's

        For more details, see:
        https://discordpy.readthedocs.io/en/latest/api.html#discord.Embed
        """
        # import moved to avoid circular import
        from .parser import SlackParser

        link = MessageLink(
            title=link_dict.get('title'),
            title_link=SlackParser.unescape_url(link_dict.get('title_link')),
            text=link_dict.get('text'),
            service_name=link_dict.get('service_name'),
            service_icon=SlackParser.unescape_url(link_dict.get('service_icon')),
            image_url=SlackParser.unescape_url(link_dict.get('image_url')),
            thumb_url=SlackParser.unescape_url(link_dict.get('thumb_url')),
        )

        if logger.level == logging.DEBUG:
            logger.debug(f"Link added to parsed message: {link}")
        else:
            logger.info(f"Link added to parsed message: {link.title_link}")

        self.links.append(link)

    def add_file(self, file_dict: dict[str, str]) -> None:
        """
        Add the info for a file to the parsed message

        This is stored internally as self.files, which is a list of MessageFile

        For more details, see:
        https://discordpy.readthedocs.io/en/latest/api.html#discord.Message.add_files
        https://discordpy.readthedocs.io/en/latest/api.html#discord.File
        """
        # import moved to avoid circular import
        from .parser import SlackParser

        file = MessageFile(
            id=file_dict['id'],
            name=file_dict['name'],
            url=cast(str, SlackParser.unescape_url(file_dict['url_private'])),
        )

        if logger.level == logging.DEBUG:
            logger.debug(f"File added to parsed message: {file}")
        else:
            logger.info(f"File added to parsed message: {file.name}")

        self.files.append(file)

    def __repr__(self) -> str:
        return f"ParsedMessage(text='{self.text}', links={self.links}, files={self.files})"

    def get_discord_send_kwargs(self) -> dict[str, Union[str, Optional[list[discord.Embed]]]]:
        """
        Return the details of the ParsedMessage object as a Discord specific dict of kwargs

        This can be passed via the send(**kwargs) method for a Discord text channel or thread.

        For more details, see:
        https://discordpy.readthedocs.io/en/latest/api.html#discord.TextChannel.send
        https://discordpy.readthedocs.io/en/latest/api.html#discord.Thread.send
        https://discordpy.readthedocs.io/en/latest/api.html#discord.Embed
        """
        if self.links:
            if len(self.links) > MAX_DISCORD_EMBEDS:
                logger.warning(f"Number of links ({len(self.links)} exceeds the Discord max"
                               f" ({MAX_DISCORD_EMBEDS}), truncating list")

            embeds = []
            for link in self.links[:min(len(self.links), MAX_DISCORD_EMBEDS)]:
                # here is where we have to translate terminology from Slack to Discord
                embed = discord.Embed(
                    title=link.title,
                    url=link.title_link,
                    description=link.text,
                )

                if link.service_name or link.service_icon:
                    embed.set_author(
                        name=link.service_name,
                        icon_url=link.service_icon,
                    )
                if link.image_url:
                    embed.set_image(url=link.image_url)
                if link.thumb_url:
                    embed.set_thumbnail(url=link.thumb_url)

                embeds.append(embed)

        else:
            # no links
            embeds = None

        return {
            'content': self.text,
            'embeds': embeds,
        }

    def get_discord_add_files_args(self) -> Optional[list[discord.File]]:
        """
        Return the list of MessageFile objects within a ParsedMessage object as a Discord
        specific list of args

        This can be passed via the method Messsage.add_files(*files), assuming the caller has
        a Discord Message object

        Any files which were not found and previously ignored are excluded

        If there are no files, return None

        For more details, see:
        https://discordpy.readthedocs.io/en/latest/api.html#discord.Message.add_files
        https://discordpy.readthedocs.io/en/latest/api.html#discord.File
        """
        if not self.files:
            return None

        return [discord.File(str(file.local_filename),  # this is the actual file to upload
                                                        #     should be set by now
                             filename=file.name)        # this is what Discord should call the file
                for file in self.files
                if not file.not_found]             # exclude files not found


class MessageLink():
    """
    Properties from an exported Slack message to support a link

    The internal naming conventions within here are all based on Slack

    Slack calls a link an 'attachment', Discord calls it an 'Embed'
    """
    def __init__(
            self,
            title: Optional[str] = None,
            title_link: Optional[str] = None,
            text: Optional[str] = None,
            service_name: Optional[str] = None,
            service_icon: Optional[str] = None,
            image_url: Optional[str] = None,
            thumb_url: Optional[str] = None
    ) -> None:
        # these are all based on Slack terminology
        self.title = title
        self.title_link = title_link
        self.text = text
        self.service_name = service_name
        self.service_icon = service_icon
        self.image_url = image_url
        self.thumb_url = thumb_url

    def __repr__(self) -> str:
        return (f"MessageLink(title='{ParsedMessage.str_or_none(self.title)}',"
                f" title_link='{ParsedMessage.str_or_none(self.title_link)}',"
                f" text='{ParsedMessage.str_or_none(self.text)}',"
                f" service_name='{ParsedMessage.str_or_none(self.service_name)}',"
                f" service_icon='{ParsedMessage.str_or_none(self.service_icon)}',"
                f" image_url='{ParsedMessage.str_or_none(self.image_url)}',"
                f" thumb_url='{ParsedMessage.str_or_none(self.thumb_url)}')")


class MessageFile():
    """
    Properties from an exported Slack message to support an attached file
    """
    def __init__(self, id: str, name: str, url: str) -> None:
        self.id = id      # from slack
        self.name = name
        self.url = url    # url_private in slack
        # This will be set later, when the file is downloaded (successfully or not)
        self.local_filename: Optional[str] = None
        # This is set in the special case of the file not found,
        # which the user can optionally ignore.
        self.not_found = False

    def __repr__(self) -> str:
        return (f"MessageFile(id='{self.id}',"
                f" name='{self.name}',"
                f" url='{self.url}',"
                f" local_filename={ParsedMessage.str_or_none(self.local_filename)}),"
                f" not_found={self.not_found})")
