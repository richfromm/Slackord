from datetime import datetime
import json
import logging
from os import listdir
from os.path import basename, join
from re import match
import time


logger = logging.getLogger(__name__)


class SlackParser():
    """
    A parser for exported files from Slack
    to interpret the content of messages to post to Discord
    """
    def __init__(self, src_file=None, src_dir=None, dest_channel=None, verbose=False):
        self.src_file = src_file
        self.src_dir = src_dir
        self.dest_channel = dest_channel
        self.verbose = verbose
        self.parsed_messages = dict()

    @staticmethod
    def is_slack_export_filename(filename):
        """
        Check if the given filename is of the form expected for a slack export JSON file

        In practice, these should be of the form YYYY-MM-DD.json
        """
        return match('\A\d\d\d\d-\d\d-\d\d.json\Z', basename(filename))

    @staticmethod
    def format_time(timestamp):
        """
        Given a timestamp in seconds (potentially fractional) since the epoch,
        format it in a useful human readable manner
        """
        return datetime.fromtimestamp(timestamp).isoformat(sep=' ', timespec='seconds')

    @staticmethod
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
            return f"`{SlackParser.format_time(timestamp)}` **{real_name}**{message_sep}{message}"
        else:
            return f"`{SlackParser.format_time(timestamp)}`{message_sep}{message}"

    def parse(self):
        """
        Parse a Slack export.

        Whether this is a single file, or an entire dir, depends on the configuration that was
        passed in during initialization.
        """
        if self.src_dir:
            self.parse_channel(self.src_dir)
        elif self.src_file:
            self.parse_file(self.src_file)
        else:
            logger.error("Neither src dir nor file set, will not parse")

    def parse_channel(self, channel_dir):
        """
        Parse all of the files in a single dir corresponding to one slack channel

        Each file corresponds to a single day for that channel
        """
        # infer the dest Discord channel if needed
        if not self.dest_channel:
            self.dest_channel = basename(channel_dir)
            logger.info(f"Inferring dest Discord channel: {self.dest_channel}")

        # these are the basename's only (not including the dir)
        # this list is not sorted
        filenames = [filename
                     for filename in listdir(path=channel_dir)
                     if SlackParser.is_slack_export_filename(filename)]

        # sort the list so that we parse all of the files for a single channel in date order
        for filename in sorted(filenames):
            self.parse_file(join(channel_dir, filename))

    def parse_file(self, filename):
        """
        Parse a single JSON file that contains exported messages from a slack channel

        In practice, one file corresponds to a single calendar day of activity

        Compile a dict where:
        - the keys are the timestamps of the slack messages
        - the values are tuples of length 2
          - the first item is the formatted string of a message ready to post to discord
          - the second item is a dict if this message has a thread, otherwise None.
            - the keys are the timestamps of the messages within the thread
            - the values are the formatted strings of the messages within the thread

        The dict is assembled in self.parsed_messages (not returned)
        """
        logger.info(f"Parsing JSON Slack export file: {filename}")

        if not SlackParser.is_slack_export_filename(filename):
            logger.warn(f"Filename is not named as expected, will try to parse anyway: {filename}")

        with open(filename) as f:
            for message in json.load(f):
                if 'user_profile' in message and 'ts' in message and 'text' in message:
                    timestamp = float(message['ts'])
                    real_name = message['user_profile']['real_name']
                    message_text = message['text']
                    full_message_text = SlackParser.format_message(timestamp, real_name, message_text)

                    if 'replies' in message:
                        # this is the head of a thread
                        self.parsed_messages[timestamp] = (full_message_text, dict())
                    elif 'thread_ts' in message:
                        # this is within a thread
                        thread_timestamp = float(message['thread_ts'])
                        if thread_timestamp not in self.parsed_messages:
                            # can't find the root of the thread to which this message belongs
                            # ideally this shouldn't happen
                            # but it could if you have a long enough message history not captured in the exported file
                            logger.warning(f"Can't find thread with timestamp {thread_timestamp} for message with timestamp {timestamp},"
                                           " creating synthetic thread")
                            fake_message_text = SlackParser.format_message(
                                thread_timestamp, None, '_Unable to find start of exported thread_')
                            self.parsed_messages[thread_timestamp] = (fake_message_text, dict())

                        # add to the dict either for the existing thread
                        # or the fake thread that we created above
                        self.parsed_messages[thread_timestamp][1][timestamp] = full_message_text
                    else:
                        # this is not associated with a thread at all
                        self.parsed_messages[timestamp] = (full_message_text, None)

        logger.info("Messages from Slack export successfully parsed.")
        self.output_messages()

    def output_messages(self):
        """
        Log the parsed messages (or a summary)
        """
        verbose_substr = "The following" if self.verbose else "A total of"
        logger.info(f"{verbose_substr} {len(self.parsed_messages)} messages"
                    " (plus thread contents if applicable) have been parsed")
        if not self.verbose:
            return

        for timestamp in sorted(self.parsed_messages.keys()):
            (message, thread) = self.parsed_messages[timestamp]
            logger.info(message)
            if thread:
                for timestamp_in_thread in sorted(thread.keys()):
                    thread_message = thread[timestamp_in_thread]
                    logger.info(f"\t{thread_message}")
