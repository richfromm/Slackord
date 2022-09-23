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

    def __repr__(self):
        return f"ParsedMessage(text='{self.text}')"

    def get_discord_send_kwargs(self):
        """
        Return the details of the ParsedMessage object as a Discord specific dict of kwargs

        This can be passed via the send(**kwargs) method for a Discord text channel or thread.

        For more details, see:
        https://discordpy.readthedocs.io/en/latest/api.html#discord.TextChannel.send
        https://discordpy.readthedocs.io/en/latest/api.html#discord.Thread.send
        """
        return {'content': self.text}
