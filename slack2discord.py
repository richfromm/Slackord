#!/usr/bin/env python

# This is originally based on Slackord, by Thomas Loupe
# Enough chaanges led to a hard fork, it is now slack2discord, by Rich Fromm

import asyncio
import logging
from sys import argv, exit

from discord.utils import setup_logging

from slack2discord.client import DiscordClient
from slack2discord.config import get_config
from slack2discord.downloader import SlackDownloader
from slack2discord.parser import SlackParser


logger = logging.getLogger('slack2discord')


if __name__ == '__main__':
    # Normally logging gets set up automatically when discord.Client.run() is called.
    # But we want to use logging before then, with the same config.
    # So set it up manually.
    setup_logging(root=True)

    config = get_config(argv)
    if config.verbose:
        logger.info("Verbose output enabled, setting log level to DEBUG")
        logger.setLevel(logging.DEBUG)

    # parse either a single file (one day of one Slack channel),
    # or all of the files in a dir (all days for one Slack channel)
    parser = SlackParser(
        src_file=config.src_file,
        src_dir=config.src_dir,
        dest_channel=config.dest_channel,
        src_dirtree=config.src_dirtree,
        channel_file=config.channel_file,
        users_file=config.users_file,
        verbose=config.verbose,
    )
    parser.parse()

    downloader = SlackDownloader(
        parsed_messages=parser.parsed_messages,
        downloads_dir=config.downloads_dir,
    )
    downloader.download()

    # post the parsed Slack messages to Discord channel(s)
    client = DiscordClient(
        token=config.token,
        parsed_messages=parser.parsed_messages,
        server_name=config.server,
        create_channels=config.create,
        verbose=config.verbose,
        dry_run=config.dry_run,
    )
    # if Ctrl-C is pressed, we do *not* get a KeyboardInterrupt
    # b/c it is caught by the run() loop in the discord client
    client.run()

    # XXX return values of asyncio functions are tricky, don't worry about it for now
    #     we could set a boolean on success within the client
    logger.info("Discord import from Slack export complete (may or may not have been successful)")
    exit(0)
