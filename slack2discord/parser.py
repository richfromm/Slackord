from datetime import datetime
import json
import logging
from os import listdir
from os.path import basename, join, isdir, realpath
from re import match, sub

from .message import ParsedMessage


logger = logging.getLogger(__name__)


class SlackParser():
    """
    A parser for exported files from Slack
    to interpret the content of messages to post to Discord
    """
    def __init__(self,
                 src_file=None, src_dir=None, dest_channel=None,
                 src_dirtree=None, channel_file=None,
                 verbose=False):
        # These are from the config, some will be None
        self.src_file = src_file
        # canonicalize path to properly infer channel name in non-obvious situations, e.g. dir ends
        # in path separator, minimal relative paths (e.g. '.' or '..')
        self.src_dir = realpath(src_dir) if src_dir else None
        self.dest_channel = dest_channel
        self.src_dirtree = realpath(src_dirtree) if src_dirtree else None
        self.channel_file = channel_file
        self.verbose = verbose

        # See set_channel_map() for details
        self.channel_map = dict()

        # See parse() for details
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
    def format_message(timestamp, name, message):
        """
        Given a timestamp, name, and message from slack,
        format it into a message to post to discord
        """
        # if the message spans multiple lines, output it starting on a separate line from the header
        if message.find('\n') != -1:
            message_sep = '\n'
        else:
            message_sep = ' '

        if name:
            return f"`{SlackParser.format_time(timestamp)}` **{name}**{message_sep}{message}"
        else:
            return f"`{SlackParser.format_time(timestamp)}`{message_sep}{message}"

    @staticmethod
    def unescape_url(url):
        """
        The Slack export escapes all slashes (/) in URL's with a backslash (\/). Undo this.

        Return the unescaped string.
        """
        if url is None:
            return None

        # There's really only a single backslash in the input escape,
        # but we need to deal with some escaping hell in specifying this,
        # hence the triple backslash here.
        #
        # This will perform multiple substitutions, across multiple lines, if needed.
        return sub('\\\/', '/', url)

    @staticmethod
    def unescape_text(text):
        """
        The slack export converts slack control characters to HTML entities. Undo this.

        Return the unescaped string.

        * ampersand (&) is (&amp;)
        * less than sign (<) is (&lt;)
        * greater than sign (>) is (&gt;)

        For more details, see:
        https://api.slack.com/reference/surfaces/formatting#escaping
        """
        unescaped_amp = sub('&amp;', '&', text)
        unescaped_amp_lt = sub('&lt;', '<', unescaped_amp)
        unescaped_amp_lt_gt = sub('&gt;', '>', unescaped_amp_lt)

        return unescaped_amp_lt_gt

    @staticmethod
    def fix_markdown(text):
        """
        Fix some non-standard Slack Markdown syntax

        Return the transformed text string.
        This works across multiple lines.

        This addresses the following non-standard Slack Markdown:
        * Slack uses *one* asterisk for bold, standard (and Discord) is **two**

          (One asterisk is standard Markdown for italic. Thankfully, the alternative of _one_
          underscore works in both Slack and Discord, so there is nothing to do here.)

        * Slack uses ~one~ tilde for strikethrough, standard (and Discord) is ~~two~~

        For more details, see:
        * https://www.markdownguide.org/tools/slack/
        * https://www.markdownguide.org/tools/discord/
        """
        # The asterisk for bold needs to be escape in the regex, b/c otherwise it means "0 or more"
        # It does *not* need to be escaped in the substitution string
        SLACK_BOLD_RE = "(\*)(\S+|\S.*\S)(\*)"
        DISCORD_BOLD_SUB = r"\1*\2*\3"
        text_bold_fixed = sub(
            SLACK_BOLD_RE, DISCORD_BOLD_SUB, text)

        # A tilde for strikethrough is not a regex special char, so needs no escaping
        SLACK_STRIKETHROUGH_RE = "(~)(\S+|\S.*\S)(~)"
        DISCORD_STRIKETHROUGH_SUB = r"\1~\2~\3"
        text_bold_and_strikethrough_fixed = sub(
            SLACK_STRIKETHROUGH_RE, DISCORD_STRIKETHROUGH_SUB, text_bold_fixed)

        return text_bold_and_strikethrough_fixed

    def get_name(self, message, timestamp, filename):

        """
        Given a message from slack, return a name to be used in formatting a message for discord.
        """
        user_profile = message.get('user_profile')
        if user_profile:
            display_name = user_profile.get('display_name')
            if display_name:
                return display_name
            real_name = user_profile.get('real_name')
            if real_name:
                return real_name

        user = message.get('user')
        if user:
            if user.startswith('U'):
                # stip leading U
                return user[1:]
            return user

        logger.warning(f"Unable to find a user to display for message with timestamp {timestamp}"
                       f" in file {filename}")
        return '???'

    def set_channel_map(self):
        """
        Populate a dict where the keys are Slack channel names and the values are corresponding
        Discord channel names.

        If the channel names are the same in Slack and Discord, a value can be the same as a key.

        The dict will have multiple items only in the src_dirtree case.

        In both the src_dir and src_file cases, there is only one item.

        In the src_file case, the key is None, and it's only the value that matters.

        Does not return anything, the results populate the class member self.channel_map
        """
        def canonicalize(channel_name):
            """
            Strip the leading pound sign (#) if present in a channel name
            """
            if channel_name.startswith('#'):
                return channel_name[1:]

            return channel_name

        if self.src_dir and not self.dest_channel:
            # infer the dest Discord channel
            self.dest_channel = basename(self.src_dir)
            logger.info(f"Inferring dest Discord channel: {self.dest_channel}")

        if self.src_file:
            # one channel only, one file
            self.channel_map[None] = canonicalize(self.dest_channel)

        elif self.src_dir:
            # one channel only, one dir
            self.channel_map[basename(self.src_dir)] = canonicalize(self.dest_channel)

        elif self.src_dirtree:
            # multiple channels

            # get the list of all slack channels from the list of subdirs in the export.
            # we could also get this by parsing the `name` attributes in the channels.json file.
            # we need this for the case with no channel file.
            # we do this for both cases to verify that slack channels in the channel file exist in
            # the slack export.
            all_slack_channels = [subdir
                                  for subdir in listdir(path=self.src_dirtree)
                                  if isdir(join(self.src_dirtree, subdir))]

            if self.channel_file:
                # if there is a channel file, parse the file
                with open(self.channel_file) as _file:
                    for line in _file:
                        fields = line.strip().split()
                        if len(fields) == 0:
                            # empty line, okay, skip
                            pass
                        elif len(fields) > 2:
                            raise RuntimeException(
                                "Line in file mapping Slack to Discord channels has too many"
                                f" fields: {fields}")
                        else:
                            slack_channel = canonicalize(fields[0])
                            if slack_channel not in all_slack_channels:
                                raise ValueError(
                                    f"Slack channel {slack_channel} from channel file"
                                    f" {self.channel_file} is not in the slack export at"
                                    f" {self.src_dirtree}")
                            if len(fields) == 1:
                                # slack channel only, discord channel is same
                                self.channel_map[slack_channel] = slack_channel
                            else:
                                # map of slack to discord channel
                                discord_channel = canonicalize(fields[1])
                                self.channel_map[slack_channel] = discord_channel

            else:
                # if there is not a channel file, include all slack channels, with the same name in
                # discord.
                for slack_channel in all_slack_channels:
                    self.channel_map[slack_channel] = slack_channel
        else:
            # this shouldn't happen
            raise RuntimeError("No channel related option type is set, can't set channel map")

        logger.info(f"Mapping of Slack to Discord channel(s): {self.channel_map}")

    def parse(self):
        """
        Parse a Slack export, and populate a dict with its contents.

        Whether this is a single file, or an entire dir, depends on the configuration that was
        passed in during initialization.

        The structure of the dict is somewhat complicated.

        The keys are Discord channel names.
        The values are dicts, where:
        - the keys are the timestamps of the slack messages
        - the values are tuples of length 2
          - the first item is the formatted string of a message ready to post to discord
          - the second item is a dict if this message has a thread, otherwise None.
            - the keys are the timestamps of the messages within the thread
            - the values are the formatted strings of the messages within the thread

        Does not return anything, the results populate the class member self.parsed_messages
        """
        self.set_channel_map()
        for slack_channel, discord_channel in self.channel_map.items():
            self.parse_channel(slack_channel, discord_channel)

        logger.info("Messages from Slack export successfully parsed.")

    def parse_channel(self, slack_channel, discord_channel):
        """
        Parse all of the files that we will import to a single Discord channel.

        This could be either all of the files in a single dir corresponding to one Slack channel,
        or just a single file explicitly specified (from one Slack channel).

        In the single file case, slack_channel is None.

        Each file corresponds to a single day for a single Slack channel.

        Does not return anything, the results populate the class member self.parsed_messages
        See parse() above for more details.
        """
        channel_msgs_dict = dict()

        if slack_channel:
            # parse all of the files in a dir for a single slack channel
            logger.info(f"Parsing Slack channel {slack_channel} from export, to import to Discord"
                        f" channel {discord_channel}")
            if self.src_dirtree:
                channel_dir = join(self.src_dirtree, slack_channel)
            else:
                assert self.src_dir, f"No slack source dir tree or source dir is set for slack channel {slack_channel}"
                channel_dir = self.src_dir

            # these are the basename's only (not including the dir)
            # this list is not sorted
            filenames = [filename
                         for filename in listdir(path=channel_dir)
                         if SlackParser.is_slack_export_filename(filename)]
            if not filenames:
                logger.warning("Unable to find any slack export JSON files for slack channel"
                               f" {slack_channel} in dir {channel_dir}")
                # XXX or should this be fatal and raise an Exception ?
                return

            # sort the list so that we parse all of the files for a single channel in date order
            for filename in sorted(filenames):
                self.parse_file(join(channel_dir, filename), channel_msgs_dict)

        else:
            # if no slack channel is set, then there is only a single file to parse
            # this should only happen in the single file case
            assert self.src_file, "No slack channel is set, but neither is a source file"
            logger.info(f"Parsing a single Slack export file only {self.src_file}, to import to"
                        f" Discord channel {discord_channel}")
            self.parse_file(self.src_file, channel_msgs_dict)

        self.output_messages(discord_channel, channel_msgs_dict)
        self.parsed_messages[discord_channel] = channel_msgs_dict

    def parse_file(self, filename, channel_msgs_dict):
        """
        Parse a single JSON file that contains exported messages from a slack channel.

        In practice, one file corresponds to a single calendar day of activity.

        The messages are added to the passed in dict for that channel.
        The dict itself is a value from the self.parsed_messages dict.
        See parse() above for more details.

        Does not return anything, channel_msgs_dict is populated in place.
        """
        logger.info(f"Parsing Slack export JSON file: {filename}")

        if not SlackParser.is_slack_export_filename(filename):
            logger.warning("Filename is not named as expected, will try to parse anyway:"
                           f" {filename}")

        with open(filename) as _file:
            for message in json.load(_file):
                self.parse_message(message, filename, channel_msgs_dict)

        logger.info(f"Messages from Slack export file successfully parsed: {filename}")

    def parse_message(self, message, filename, channel_msgs_dict):
        """
        Parse a single message that was loaded from the JSON file with the given filename.

        Add the message as appropriate to the passed in dict for a particular channel.
        See parse() above for more details.

        Does not return anything, channel_msgs_dict is populated in place.

        For some pseudo-documentation on message format, see:
        https://slack.com/help/articles/220556107-How-to-read-Slack-data-exports#how-to-read-messages
        """
        if message.get('type') != 'message':
            return

        if 'ts' not in message:
            # According to the docs, 'ts' should always be present
            logger.warning("Message is missing timestamp, skipping.")
            return

        timestamp = float(message['ts'])
        name = self.get_name(message, timestamp, filename)
        # According to the docs, 'text' should always be present.  And in practice,
        # even for no text (possible in a file attachment case, which is not yet
        # supported), the key should be present, with an empty string value.
        # Regardless, provide an empty string as a default value just in case it's not
        # present.
        message_text = SlackParser.fix_markdown(
            SlackParser.unescape_text(
            SlackParser.unescape_url(
            message.get('text', ""))))
        full_message_text = SlackParser.format_message(timestamp, name, message_text)
        parsed_message = ParsedMessage(full_message_text)
        if 'attachments' in message:
            for attachment in message['attachments']:
                parsed_message.add_link(attachment)

        if 'replies' in message:
            # this is the head of a thread
            channel_msgs_dict[timestamp] = (parsed_message, dict())
        elif 'thread_ts' in message:
            # this is within a thread
            thread_timestamp = float(message['thread_ts'])
            if thread_timestamp not in channel_msgs_dict:
                # can't find the root of the thread to which this message belongs
                # ideally this shouldn't happen
                # but it could if you have a long enough message history not captured in the exported file
                logger.warning(f"Can't find thread with timestamp {thread_timestamp} for"
                               f" message with timestamp {timestamp}, creating"
                               " synthetic thread")
                fake_message_text = SlackParser.format_message(
                    thread_timestamp, None, '_Unable to find start of exported thread_')
                channel_msgs_dict[thread_timestamp] = (parsed_message, dict())

            # add to the dict either for the existing thread
            # or the fake thread that we created above
            channel_msgs_dict[thread_timestamp][1][timestamp] = parsed_message
        else:
            # this is not associated with a thread at all
            channel_msgs_dict[timestamp] = (parsed_message, None)

    def output_messages(self, discord_channel, channel_msgs_dict):
        """
        Log the parsed messages (or a summary) for a single channel
        """
        verbose_substr = "The following" if self.verbose else "A total of"
        logger.info(f"{verbose_substr} {len(channel_msgs_dict)} messages (plus thread contents if"
                    f" applicable) have been parsed for Discord channel {discord_channel}")
        if not self.verbose:
            return

        for timestamp in sorted(channel_msgs_dict.keys()):
            (message, thread) = channel_msgs_dict[timestamp]
            logger.info(message)
            if thread:
                for timestamp_in_thread in sorted(thread.keys()):
                    thread_message = thread[timestamp_in_thread]
                    logger.info(f"\t{thread_message}")
