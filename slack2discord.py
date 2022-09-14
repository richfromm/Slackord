#!/usr/bin/env python

# This is originally based on Slackord, by Thomas Loupe
# Enough chaanges led to a hard fork, it is now slack2discord, by Rich Fromm

import asyncio
import logging
from sys import argv, exit

from discord.utils import setup_logging

from slack2discord.client import DiscordClient
from slack2discord.config import get_config
from slack2discord.parser import SlackParser


logger = logging.getLogger('slack2discord')


if __name__ == '__main__':
    # Normally logging gets set up automatically when discord.Client.run() is called.
    # But we want to use logging before then, with the same config.
    # So set it up manually.
    setup_logging(root=True)

    config = get_config(argv)

    # XXX this is a WIP
    if config.src_dir:
        raise NotImplementedError("--src_dir (one channel) not yet implemented")
    if config.src_dirtree:
        raise NotImplementedError("--src_dirtree (multiple channels) not yet implemented")
    if config.dry_run:
        raise NotImplementedError("--dry_run not yet implemented")

    parser = SlackParser(config.verbose)
    parser.parse_json_slack_export(config.src_file)

    client = DiscordClient(config.token, config.dest_channel, parser.parsed_messages, config.verbose)
    # if Ctrl-C is pressed, we do *not* get a KeyboardInterrupt b/c it is caught by the run() loop in the discord client
    client.run()

    # XXX return values of asyncio functions are tricky, don't worry about it for now
    logger.info("Discord import from Slack export complete (may or may not have been successful)")
    exit(0)
