#!/usr/bin/env python

# This is originally based on Slackord, by Thomas Loupe
# Enough chaanges led to a hard fork, it is now slack2discord, by Rich Fromm

import asyncio
from datetime import datetime
import discord
from discord.ext import commands
import json
import logging
from sys import argv, exit
import time


#from slack2discord.client import Slack2DiscordClient
#from .client import Slack2DiscordClient
#from . import Slack2DiscordClient
import client

logger = logging.getLogger('slack2discord')


def format_time(timestamp):
    """
    Given a timestamp in seconds (potentially fractional) since the epoch,
    format it in a useful human readable manner
    """
    return datetime.fromtimestamp(timestamp).isoformat(sep=' ', timespec='seconds')


def format_message(timestamp, real_name, message):
    """
    Given a timestamp, real name, and message from slack,
    format it into a message to post to discord
    """
    # if the message spans multiple lines, output it starting on a separate line from the header
    if message.find('\n') != -1:
        message_sep = '\n'
    else:
        message_sep = ' '

    if real_name:
        return f"`{format_time(timestamp)}` **{real_name}**{message_sep}{message}"
    else:
        return f"`{format_time(timestamp)}{message_sep}{message}"


def parse_json_slack_export(filename):
    """
    Parse a JSON file that contains the exported messages from a slack channel

    Return a dict where:
    - the keys are the timestamps of the slack messages
    - the values are tuples of length 2
      - the first item is the formatted string of a message ready to post to discord
      - the second item is a dict if this message has a thread, otherwise None.
        - the keys are the timestamps of the messages within the thread
        - the values are the formatted strings of the messages within the thread
    """
    parsed_messages = dict()
    with open(filename) as f:
        for message in json.load(f):
            if 'user_profile' in message and 'ts' in message and 'text' in message:
                timestamp = float(message['ts'])
                real_name = message['user_profile']['real_name']
                message_text = message['text']
                full_message_text = format_message(timestamp, real_name, message_text)

                if 'replies' in message:
                    # this is the head of a thread
                    parsed_messages[timestamp] = (full_message_text, dict())
                elif 'thread_ts' in message:
                    # this is within a thread
                    thread_timestamp = float(message['thread_ts'])
                    if thread_timestamp not in parsed_messages:
                        # can't find the root of the thread to which this message belongs
                        # ideally this shouldn't happen
                        # but it could if you have a long enough message history not captured in the exported file
                        logger.warning(f"Can't find thread with timestamp {thread_timestamp} for message with timestamp {timestamp},"
                                       " creating synthetic thread")
                        fake_message_text = format_message(
                            thread_timestamp, None, '_Unable to find start of exported thread_')
                        parsed_messages[thread_timestamp] = (fake_message_text, dict())

                    # add to the dict either for the existing thread
                    # or the fake thread that we created above
                    parsed_messages[thread_timestamp][1][timestamp] = full_message_text
                else:
                    # this is not associated with a thread at all
                    parsed_messages[timestamp] = (full_message_text, None)

    logger.info("Messages from Slack export successfully parsed.")
    return parsed_messages


def output_messages(parsed_messages, verbose):
    """
    Output the parsed messages to stdout
    """
    verbose_substr = " the following" if verbose else " "
    logger.info(f"Slackord will post{verbose_substr}{len(parsed_messages)} messages"
                " (plus thread contents if applicable) to your desired Discord channel")
    if not verbose:
        return

    for timestamp in sorted(parsed_messages.keys()):
        (message, thread) = parsed_messages[timestamp]
        logger.info(message)
        if thread:
            for timestamp_in_thread in sorted(thread.keys()):
                thread_message = thread[timestamp_in_thread]
                logger.info(f"\t{thread_message}")


def post_to_discord(token, channel_id, parsed_messages, verbose):
    """
    Iterate through the results of previously parsing the JSON file from a Slack export and post
    each message to Discord in the channel corresponding to the given id. Threading is preserved.
    """
    discord_client = client.Slack2DiscordClient(channel_id, parsed_messages, verbose, intents=discord.Intents.default())
    # if Ctrl-C is pressed, we do *not* get a KeyboardInterrupt b/c it is caught by the run() loop in the discord client
    discord_client.run(token)


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

    parsed_messages = parse_json_slack_export(filename)
    output_messages(parsed_messages, verbose)
    post_to_discord(token, channel_id, parsed_messages, verbose)
    # XXX return values of asyncio functions are tricky, don't worry about it for now
    logger.info("Discord import complete (may or may not have been successful)")
    exit(0)
