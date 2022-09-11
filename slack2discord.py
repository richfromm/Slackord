#!/usr/bin/env python

# This is originally based on Slackord, by Thomas Loupe
# Enough chaanges led to a hard fork, it is now slack2discord, by Rich Fromm

import asyncio
import logging
from sys import argv, exit

import discord
from discord.ext import commands

from slack2discord.client import DiscordClient
from slack2discord.parser import SlackParser


logger = logging.getLogger('slack2discord')


def post_to_discord(token, channel_id, parsed_messages, verbose):
    """
    Iterate through the results of previously parsing the JSON file from a Slack export and post
    each message to Discord in the channel corresponding to the given id. Threading is preserved.
    """
    client = DiscordClient(channel_id, parsed_messages, verbose)
    # if Ctrl-C is pressed, we do *not* get a KeyboardInterrupt b/c it is caught by the run() loop in the discord client
    client.run(token)

if __name__ == '__main__':
    # Normally logging gets set up automatically when discord.Client.run() is called.
    # But we want to use logging before then, with the same config.
    # So set it up manually.
    discord.utils.setup_logging(root=True)

    # XXX eventually do real arg parsing
    if len(argv) != 4:
        print(f"Usage {argv[0]} <token> <filename> <channel_id>")
        exit(1)

    token = argv[1]
    filename = argv[2]
    channel_id = int(argv[3])
    # XXX this should be an arg, for now just edit here
    verbose = False

    parser = SlackParser(verbose)
    parser.parse_json_slack_export(filename)

    post_to_discord(token, channel_id, parser.parsed_messages, verbose)
    # XXX return values of asyncio functions are tricky, don't worry about it for now
    logger.info("Discord import complete (may or may not have been successful)")
    exit(0)
