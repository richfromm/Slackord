import pytest

from ..client import DiscordClient


class TestDiscordClient():
    @pytest.mark.parametrize("channel_name", [
        "general",
        "foo-bar",
        "foo_bar",
        "foo-_bar",
        "foo_-bar",
        "foo__bar",
        "foo-_-bar",
        "foo_-_bar",
        "foo-bar-baz",
        "foo_bar_baz",
        "foo-bar_baz",
        "foo_bar-baz",
        "a",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz1234567890-_",
        "123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789",  # noqa: E501
        "1234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890",  # noqa: E501
    ])
    def test_valid_channel_name(self, channel_name):
        """
        Test Discord channel names that pass validation
        """
        assert DiscordClient.valid_channel_name(channel_name)

    @pytest.mark.parametrize("channel_name", [
        "foo--bar",
        "foo---bar",
        "foo----bar",
        "",
        " ",
        "foo bar",
        "foo	bar",
        "foo#bar",
        "foo`-=bar",
        "foo~!@#$%^&*()_+bar",
        r"foo[]\;',./bar",  # don't want the backslash to be treated as an escape
        'foo{}|:"<>?bar',
        "12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901",  # noqa: E501
    ])
    def test_invalid_channel_name(self, channel_name):
        """
        Test Discord channel names that fail validation
        """
        assert not DiscordClient.valid_channel_name(channel_name)
