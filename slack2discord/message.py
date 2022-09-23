import logging

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
    def __init__(self, text):
        self.text = text
        self.links = []

    def add_link(self, link_dict):
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

    def __repr__(self):
        return f"ParsedMessage(text='{self.text}', links='{self.links})"

    def get_discord_send_kwargs(self):
        """
        Return the details of the ParsedMessage object as a Discord specific dict of kwargs

        This can be passed via the send(**kwargs) method for a Discord text channel or thread.

        For more details, see:
        https://discordpy.readthedocs.io/en/latest/api.html#discord.TextChannel.send
        https://discordpy.readthedocs.io/en/latest/api.html#discord.Thread.send
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

class MessageLink():
    """
    Properties from an exported Slack message to support a link

    The internal naming conventions within here are all based on Slack

    Slack calls a link an 'attachment', Discord calls it an 'Embed'
    """
    def __init__(self,
                 title=None,
                 title_link=None,
                 text=None,
                 service_name=None,
                 service_icon=None,
                 image_url=None,
                 thumb_url=None):
        # these are all based on Slack terminology
        self.title = title
        self.title_link = title_link
        self.text = text
        self.service_name = service_name
        self.service_icon = service_icon
        self.image_url = image_url
        self.thumb_url = thumb_url

    def __repr__(self):
        return (f"MessageLink(title='{self.title}',"
                f" title_link='{self.title_link}',"
                f" text='{self.text}',"
                f" service_name='{self.service_name}',"
                f" service_icon='{self.service_icon}',"
                f" image_url='{self.image_url}',"
                f" thumb_url='{self.thumb_url}')")
