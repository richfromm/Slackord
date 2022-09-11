from datetime import datetime
import json
import logging
import time


logger = logging.getLogger(__name__)


class SlackParser():
    """
    A parser for exported files from Slack
    to interpret the content of messages to post to Discord
    """
    def __init__(self, verbose):
        self.verbose = verbose
        self.parsed_messages = dict()

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

    def parse_json_slack_export(self, filename):
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
