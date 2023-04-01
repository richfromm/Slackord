from os.path import dirname, join

from ..message import ParsedMessage
from ..parser import SlackParser, RootPlusThreadType, MessagesPerChannelType


class TestParser():
    """
    Test parsing a slack export
    """
    def _get_dict_values_sorted_by_keys(self, dict_in: dict) -> list:
        return [dict_in[key]
                for key in sorted(dict_in.keys())]

    def _parsed_message_text_ends_with(self, parsed_message: ParsedMessage, text: str) -> bool:
        """
        Does the given ParsedMessage have a text that ends with the given string

        Namely is the actual original text that, not counting any prepended headers
        """
        return parsed_message.text.endswith(text)

    def test_basic(self):
        """
        This is a simple test containing one message root without a thread,
        followed by a thread with a root and two messages in the thread.
        """
        this_dir = dirname(__file__)
        export_dir = join(this_dir, "exports", "basic")

        parser: SlackParser = SlackParser(src_dirtree=export_dir)
        parser.parse()

        # we have one channel in this test
        channel_name = 'test-slack2discord'
        channels = list(parser.parsed_messages.keys())
        assert len(channels) == 1
        assert channels[0] == channel_name

        messages_per_channel: MessagesPerChannelType = parser.parsed_messages[channel_name]
        # there is one message without a thread, plus one thread
        assert len(messages_per_channel) == 2

        sorted_roots_and_threads_by_timestamp: list[RootPlusThreadType] \
            = self._get_dict_values_sorted_by_keys(messages_per_channel)
        root_no_thread_root, root_no_thread_thread = sorted_roots_and_threads_by_timestamp[0]
        root_plus_thread_root, root_plus_thread_thread = sorted_roots_and_threads_by_timestamp[1]

        # the first message has no thread
        assert self._parsed_message_text_ends_with(
            root_no_thread_root,
            "This is a test of a message that will not be part of a thread.")
        assert not root_no_thread_thread

        # the second message has a thread with two more messages
        assert self._parsed_message_text_ends_with(
            root_plus_thread_root,
            "This is a test of a message that will be the root of a thread,"
            " with two subsequent messages within the thread.")
        assert len(root_plus_thread_thread) == 2
        thread_msgs = self._get_dict_values_sorted_by_keys(root_plus_thread_thread)
        assert self._parsed_message_text_ends_with(
            thread_msgs[0],
            "This is the first of two messages within a thread.")
        assert self._parsed_message_text_ends_with(
            thread_msgs[1],
            "This is the second of two messages within a thread.")
