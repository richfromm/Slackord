from datetime import datetime
import json
import logging
from os import listdir
from os.path import basename, dirname, exists, join, isdir, realpath
from re import match, sub, Match
from typing import cast, Any, NewType, Optional, Union

from .message import ParsedMessage


logger = logging.getLogger(__name__)

ThreadType = NewType('ThreadType', dict[float, ParsedMessage])


class SlackParser():
    """
    A parser for exported files from Slack
    to interpret the content of messages to post to Discord
    """
    def __init__(self,
                 src_file: Optional[str] = None,
                 src_dir: Optional[str] = None,
                 dest_channel: Optional[str] = None,
                 src_dirtree: Optional[str] = None,
                 channel_file: Optional[str] = None,
                 users_file: Optional[str] = None,
                 verbose: bool = False) -> None:
        # These are from the config, some will be None
        self.src_file = src_file
        # canonicalize path to properly infer channel name in non-obvious situations, e.g. dir ends
        # in path separator, minimal relative paths (e.g. '.' or '..')
        self.src_dir = realpath(src_dir) if src_dir else None
        self.dest_channel = dest_channel
        self.src_dirtree = realpath(src_dirtree) if src_dirtree else None
        self.channel_file = channel_file

        if not users_file:
            if self.src_dirtree:
                users_file = join(self.src_dirtree, 'users.json')
            elif self.src_dir:
                users_file = join(self.src_dir, '..', 'users.json')
            elif self.src_file:
                users_file = join(dirname(self.src_file), '..', 'users.json')
            else:
                # I don't think this should be able to happen
                logger.warn("users file is not specified, and unable to figure it out")

        if users_file:
            if not exists(users_file):
                logger.warn(f"users file is not specified, unable to find a users file at our guess: {users_file}")
                users_file = None

        if users_file:
            users_file = realpath(users_file)
            logger.info(f"users file found and set to: {users_file}")

        self.users_file = users_file
        # See parse_users() for details
        self.users: dict[str, str] = dict()

        self.verbose = verbose

        # See set_channel_map() for details
        self.channel_map: dict[Optional[str], str] = dict()

        # See parse() for details
        self.parsed_messages: dict[str,
                                   dict[float,
                                        tuple[ParsedMessage,
                                              Optional[ThreadType]]]] = dict()

    @staticmethod
    def is_slack_export_filename(filename: str) -> Optional[Match]:
        """
        Check if the given filename is of the form expected for a slack export JSON file

        In practice, these should be of the form YYYY-MM-DD.json
        """
        return match('\A\d\d\d\d-\d\d-\d\d.json\Z', basename(filename))

    @staticmethod
    def format_time(timestamp: Union[int, float]) -> str:
        """
        Given a timestamp in seconds (potentially fractional) since the epoch,
        format it in a useful human readable manner
        """
        return datetime.fromtimestamp(timestamp).isoformat(sep=' ', timespec='seconds')

    @staticmethod
    def format_message(timestamp: Union[int, float], name: Optional[str], message: str) -> str:
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
    def unescape_url(url: Optional[str]) -> Optional[str]:
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
    def unescape_text(text: Optional[str]) -> Optional[str]:
        """
        The slack export converts slack control characters to HTML entities. Undo this.

        Return the unescaped string.

        * ampersand (&) is (&amp;)
        * less than sign (<) is (&lt;)
        * greater than sign (>) is (&gt;)

        For more details, see:
        https://api.slack.com/reference/surfaces/formatting#escaping
        """
        if text is None:
            return None

        unescaped_amp = sub('&amp;', '&', text)
        unescaped_amp_lt = sub('&lt;', '<', unescaped_amp)
        unescaped_amp_lt_gt = sub('&gt;', '>', unescaped_amp_lt)

        return unescaped_amp_lt_gt

    @staticmethod
    def fix_markdown(text: Optional[str]) -> Optional[str]:
        """
        Fix some non-standard Slack Markdown syntax

        Return the transformed text string.
        This works across multiple lines.

        This addresses the following non-standard Slack Markdown:
        * Slack uses *one* asterisk for bold; standard (and Discord) is **two**

          (One asterisk is standard Markdown for italic. Thankfully, the alternative of _one_
          underscore works in both Slack and Discord, so there is nothing to do for this.)

        * Slack uses ~one~ tilde for strikethrough; standard (and Discord) is ~~two~~

        For more details, see:
        * https://www.markdownguide.org/tools/slack/
        * https://www.markdownguide.org/tools/discord/
        """
        if text is None:
            return None

        # The asterisk for bold needs to be escaped in the regex, b/c otherwise it means "0 or
        # more". It does *not* need to be escaped in the substitution string.
        SLACK_BOLD_RE = "(\*)(\S+|\S.*\S)(\*)"
        DISCORD_BOLD_SUB = r"\1*\2*\3"
        text_bold_fixed = sub(
            SLACK_BOLD_RE, DISCORD_BOLD_SUB, text)

        # A tilde for strikethrough is not a regex special char, so needs no escaping.
        SLACK_STRIKETHROUGH_RE = "(~)(\S+|\S.*\S)(~)"
        DISCORD_STRIKETHROUGH_SUB = r"\1~\2~\3"
        text_bold_and_strikethrough_fixed = sub(
            SLACK_STRIKETHROUGH_RE, DISCORD_STRIKETHROUGH_SUB, text_bold_fixed)

        return text_bold_and_strikethrough_fixed

    def parse_users(self) -> None:
        """
        Parse a users.json file from a Slack export, and populate a dict with its contents.

        The dict matches Slack user ID's to names.

        Does not return anything, the results populate the class member self.users
        """
        if not self.users_file:
            logger.warn("No users file specified or deduced, will get user info from individual messages")
            return

        logger.info(f"Parsing user information from {self.users_file}")
        with open(self.users_file) as _file:
            for user in json.load(_file):
                if 'id' not in user:
                    # I don't think this ought to happen
                    logger.warn("User in Slack users file is missing ID, will ignore")
                    continue

                user_id = user['id']
                if user_id in self.users:
                    # I don't think this ought to happen
                    logger.warn(f"Duplicate Slack user ID found, will ignore repeated instances: {user_id}")
                    continue

                if 'name' in user:
                    # this appears to be the same as user['profile']['display_name']
                    user_name = user['name']
                elif 'real_name' in user:
                    # this appears to be the same as user['profile']['real_name']
                    user_name = user['real_name']
                else:
                    logger.warn(f"Unable to find name for user ID: {user_id}")
                    continue

                logger.debug(f"Setting name for user ID {user_id} to {user_name}")
                self.users[user_id] = user_name

        if self.verbose:
            logger.debug(f"{len(self.users)} users successfully parsed: {self.users}")
        else:
            logger.info(f"{len(self.users)} users successfully parsed")

    def get_name(
            self,
            message: dict[str, Union[str, list[Any], dict[str, Any]]],
            timestamp: float,
            filename: str
    ) -> str:
        """
        Given a message from slack, return a name to be used in formatting a message for discord.

        If possible, we use the dict self.users that maps Slack user ID's to names (previously
        parsed from users.json, see parse_users()) to get the user name.  We fall back to info
        within the message if that is not successful.
        """
        user_id: str = cast(str, message.get('user'))
        if user_id in self.users:
            return self.users[user_id]

        user_profile: dict[str, str] = cast(dict[str, str], message.get('user_profile'))
        if user_profile:
            display_name = user_profile.get('display_name')
            if display_name:
                return display_name
            real_name = user_profile.get('real_name')
            if real_name:
                return real_name

        if user_id:
            if user_id.startswith('U'):
                # stip leading U
                return user_id[1:]
            return user_id

        logger.warning(f"Unable to find a user to display for message with timestamp {timestamp}"
                       f" in file {filename}")
        return '???'

    def set_channel_map(self) -> None:
        """
        Populate a dict where the keys are Slack channel names and the values are corresponding
        Discord channel names.

        If the channel names are the same in Slack and Discord, a value can be the same as a key.

        The dict will have multiple items only in the src_dirtree case.

        In both the src_dir and src_file cases, there is only one item.

        In the src_file case, the key is None, and it's only the value that matters.

        Does not return anything, the results populate the class member self.channel_map
        """
        def canonicalize(channel_name: str) -> str:
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
            # self.dest_channel in theory can be None,
            # but in practice it should be set in this case
            assert self.dest_channel is not None
            self.channel_map[None] = canonicalize(cast(str, self.dest_channel))

        elif self.src_dir:
            # one channel only, one dir
            # self.dest_channel in theory can be None,
            # but in practice it should be set in this case
            assert self.dest_channel is not None
            self.channel_map[basename(self.src_dir)] = canonicalize(cast(str, self.dest_channel))

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
                            raise RuntimeError(
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

    def parse(self) -> None:
        """
        Parse a Slack export, and populate a dict with its contents.

        Whether this is a single file, or an entire dir, depends on the configuration that was
        passed in during initialization.

        The structure of the dict is somewhat complicated.

        The keys are Discord channel names.
        The values are dicts, where:
        - the keys are the timestamps of the slack messages
        - the values are tuples of length 2
          - the first item is a ParsedMessage object
          - the second item is a dict if this message has a thread, otherwise None.
            - the keys are the timestamps of the messages within the thread
            - the values are ParsedMessage objects

        Does not return anything, the results populate the class member self.parsed_messages
        """
        self.parse_users()

        self.set_channel_map()
        for slack_channel, discord_channel in self.channel_map.items():
            self.parse_channel(slack_channel, discord_channel)

        logger.info("Messages from Slack export successfully parsed.")

    def parse_channel(self, slack_channel: Optional[str], discord_channel: str) -> None:
        """
        Parse all of the files that we will import to a single Discord channel.

        This could be either all of the files in a single dir corresponding to one Slack channel,
        or just a single file explicitly specified (from one Slack channel).

        In the single file case, slack_channel is None.

        Each file corresponds to a single day for a single Slack channel.

        Does not return anything, the results populate the class member self.parsed_messages
        See parse() above for more details.
        """
        channel_msgs_dict: dict[float,
                                tuple[ParsedMessage,
                                      Optional[ThreadType]]] = dict()

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

    def parse_file(
            self,
            filename: str,
            channel_msgs_dict: dict[float,
                                    tuple[ParsedMessage,
                                          Optional[ThreadType]]]
    ) -> None:
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

    def parse_message(
            self,
            message: dict[str, Union[str, list[Any], dict[str, Any]]],
            filename: str,
            channel_msgs_dict: dict[float,
                                    tuple[ParsedMessage,
                                          Optional[ThreadType]]]
    ) -> None:
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

        # in general, values in the JSON could be lists or dicts, but in this case we know it's a
        # string representing a float
        timestamp = float(cast(str, message['ts']))
        name = self.get_name(message, timestamp, filename)
        # According to the docs, 'text' should always be present.  And in practice,
        # even for no text (possible in a file attachment case, which is not yet
        # supported), the key should be present, with an empty string value.
        # Regardless, provide an empty string as a default value just in case it's not
        # present.
        message_text: str = cast(str, SlackParser.fix_markdown(
            SlackParser.unescape_text(
                SlackParser.unescape_url(
                    cast(str, message.get('text', ""))))))
        full_message_text = SlackParser.format_message(timestamp, name, message_text)
        parsed_message = ParsedMessage(full_message_text)

        if 'attachments' in message:
            for attachment in message['attachments']:
                parsed_message.add_link(cast(dict[str, Any], attachment))

        if 'files' in message:
            for file in message['files']:
                file = cast(dict[str, Any], file)
                if file.get('mode') == 'tombstone':
                    # File was deleted from Slack, just log this,
                    # don't bother mentioning this state in the Discord import.
                    if 'date_deleted' in file:
                        logger.warning("Attached file was deleted at"
                            f" {SlackParser.format_time(cast(int, file['date_deleted']))}."
                            " Ignoring.")
                    else:
                        logger.warning(f"Attached file was deleted. Ignoring.")
                else:
                    # Normal attached file case
                    parsed_message.add_file(cast(dict[str, Any], file))

        if 'replies' in message:
            # this is the head of a thread
            empty_thread_dict: ThreadType = cast(ThreadType, dict())
            channel_msgs_dict[timestamp] = (parsed_message, empty_thread_dict)
        elif 'thread_ts' in message:
            # this is within a thread
            # in general, values in the JSON could be lists or dicts, but in this case we know it's
            # a string representing a float
            thread_timestamp = float(cast(str, message['thread_ts']))
            if thread_timestamp not in channel_msgs_dict:
                # can't find the root of the thread to which this message belongs
                # ideally this shouldn't happen
                # but it could if you have a long enough message history not captured in the exported file
                logger.warning(f"Can't find thread with timestamp {thread_timestamp} for"
                               f" message with timestamp {timestamp}, creating"
                               " synthetic thread")
                fake_message_text = SlackParser.format_message(
                    thread_timestamp, None, '_Unable to find start of exported thread_')
                fake_message = ParsedMessage(fake_message_text)
                empty_fake_thread_dict: ThreadType = cast(ThreadType, dict())
                channel_msgs_dict[thread_timestamp] = (fake_message, empty_fake_thread_dict)

            # add to the dict either for the existing thread
            # or the fake thread that we created above
            this_thread: Optional[ThreadType] = channel_msgs_dict[thread_timestamp][1]
            # in theory there might not be a thread, but in practice there should be in this case
            assert this_thread is not None
            cast(ThreadType, this_thread)[timestamp] = parsed_message
        else:
            # this is not associated with a thread at all
            channel_msgs_dict[timestamp] = (parsed_message, None)

    def output_messages(
            self,
            discord_channel: str,
            channel_msgs_dict: dict[float,
                                    tuple[ParsedMessage,
                                          Optional[ThreadType]]]
    ) -> None:
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
