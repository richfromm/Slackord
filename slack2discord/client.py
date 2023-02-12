import asyncio
from decorator import decorator
import logging
from pprint import pprint
from traceback import print_exc
from typing import Callable, Optional, Union, Sequence

import discord

from .message import ParsedMessage


logger = logging.getLogger(__name__)


# template copied from https://github.com/Rapptz/discord.py/blob/master/examples/background_task_asyncio.py
class DiscordClient(discord.Client):
    """
    A Discord client for the purposes of importing the content of messages exported from Slack
    *Not* intended to be generic
    """
    def __init__(
            self,
            token: str,
            parsed_messages: dict[str,
                                  dict[float,
                                       tuple[ParsedMessage,
                                             Optional[dict[float,
                                                           ParsedMessage]]]]],
            server_name: Optional[str] = None,
            create_channels: bool = False,
            verbose: bool = False,
            dry_run: bool = False,
            **kwargs) -> None:
        self.token: str = token

        # see SlackParser.parse() for details
        self.parsed_messages: dict[str,
                                   dict[float,
                                        tuple[ParsedMessage,
                                              Optional[dict[float,
                                                            ParsedMessage]]]]] = parsed_messages
        # name if Discord server. internally referred to as "guild".
        # optional, not needed if this client is only a member of one guild.
        self.server_name: Optional[str] = server_name
        # create Discord channels if not present. if not set, then fail in this case.
        self.create_channels: bool = create_channels
        # a mapping of discord channel names to channel objects
        self.channels: dict[str, Optional[discord.TextChannel]] = dict()

        self.verbose: bool = verbose
        self.dry_run: bool = dry_run

        if 'intents' not in kwargs:
            kwargs['intents'] = discord.Intents(
                messages=True,
                guilds=True)   # needed for Client.get_channel() and Client.get_all_channels()

        super().__init__(**kwargs)

    async def setup_hook(self) -> None:
        logger.info("In setup_hook(), creating background task")

        # create the background task and run it in the background to post all of the messages
        # the reason for saving bg_task even though we don't use it anywhere:
        # from https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
        #
        # Important Save a reference to the result of this function, to avoid a task disappearing
        # mid execution. The event loop only keeps weak references to tasks. A task that isn’t
        # referenced elsewhere may get garbage-collected at any time, even before it’s done. For
        # reliable “fire-and-forget” background tasks, gather them in a collection.
        self.bg_task = self.loop.create_task(self.post_messages())

    async def on_ready(self):
        logger.info(f"In on_ready(), logged in as {self.user} (ID: {self.user.id})")

    def run(self):
        """
        Wrapper around https://discordpy.readthedocs.io/en/latest/api.html#discord.Client.run
        using the already supplied token
        """
        super().run(self.token)

    # Different signature from superclass get_guild(id: int) and therefore different name to not collide
    def get_guild_maybe_by_name(self, guild_name: Optional[str] = None) -> discord.Guild:
        """
        Get the appropriate guild (aka server).

        If a name is supplied, use that to match. Otherwise, just check the list of available
        guilds.

        We expect one and only one matching result. Return it, as a discord.Guild object.
        https://discordpy.readthedocs.io/en/latest/api.html#guild

        Otherwise, raise a RuntimeError.
        """
        # use self.guilds rather than self.fetch_guilds() to avoid an unnecessary API call
        guilds: Sequence[discord.Guild]
        if guild_name:
            guilds = [guild
                      for guild in self.guilds
                      if guild.name == guild_name]
            xtra_error_str = f" with name {guild_name}"
        else:
            guilds = self.guilds

        if not guilds:
            error_msg = f"Unable to find Discord server{xtra_error_str}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if len(guilds) > 1:
            # I suspect this may not actually be possible in practice
            error_msg = (f"Unable to find unique Discord server{xtra_error_str}:"
                         f" {[guild.name for guild in guilds]}")
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        guild = guilds[0]
        logger.info(f"Successfully got Discord server {guild} with id {guild.id}")

        return guild

    def get_category(
            self,
            guild: discord.Guild,
            category_name: str) -> Optional[discord.CategoryChannel]:
        """
        Get the category with the specified name.

        We expect one and only one matching result. Return it, as a discord.CategoryChannel object.
        https://discordpy.readthedocs.io/en/latest/api.html#discord.CategoryChannel

        If we find multiple results, somewhat arbitrarily return the first.

        If we find no results, return None
        """
        categories = [category
                      for category in guild.categories
                      if category.name == category_name]
        if not categories:
            # Uncategorized channels appear separately in the Discord GUI
            logger.warning(f"Unable to find category with name {category_name}")
            category = None
        else:
            if len(categories) > 1:
                # I suspect this is not actually possible in practice
                logger.warning(f"Found multiple categories with name {category_name}, will"
                               " arbitrarily pick the first")
            category = categories[0]

        return category

    async def create_text_channel(
            self,
            guild: discord.Guild,
            channel_name: str,
            dry_run: bool = False) -> Optional[discord.TextChannel]:
        """
        Create a new text channel with the specified name.

        Return it, as a discord.TextChannel object.
        https://discordpy.readthedocs.io/en/latest/api.html#textchannel

        In the dry run case, return None.
        """
        logger.info(f"Creating missing Discord channel: {channel_name}")
        # We are intentionally not wrapping the following Discord API call with
        # `@discord_retry`. It's not in the actual repeated posting path, so we'd rather it
        # fail fast and not retry. This is somewhat arbitrary, and it wouldn't be wrong to
        # wrap it.
        if dry_run:
            logger.info(f"DRY_RUN: guild.create_text_channel({channel_name})")
            channel = None
        else:
            text_channels_category = self.get_category(guild, 'Text Channels')
            if not text_channels_category:
                logger.warning("Unable to find category for text channels, new channel will not be"
                               " in a category")

            # This requires the "Manage Channels" permission
            # https://discordpy.readthedocs.io/en/latest/api.html#discord.Guild.create_text_channel
            channel = await guild.create_text_channel(channel_name, category=text_channels_category)
            assert channel.name == channel_name, f"New channel has unexpected name: {channel.name}"

        return channel

    # Different signature from superclass get_channel(id: int) and therefore different name to not collide
    async def get_channel_by_name(
            self,
            guild: discord.Guild,
            channel_name: str,
            create: bool = False,
            dry_run: bool = False) -> Optional[discord.TextChannel]:
        """
        Get the channel with the specified name.

        Return it, as a discord.TextChannel object.
        https://discordpy.readthedocs.io/en/latest/api.html#textchannel

        Optionally create the channel if it does not exist.

        If the create option is not selected, and the channel does not exist, raise a RuntimeError.

        In the dry run creation case, return None.
        """
        channels = [channel
                    for channel in guild.text_channels
                    if channel.name == channel_name]
        if not channels:
            if not create:
                error_msg = f"Unable to find Discord channel {channel_name}, use --create to auto create"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            channel = await self.create_text_channel(guild, channel_name, dry_run=dry_run)

        elif len(channels) > 1:
            # I suspect this may not actually be possible in practice
            error_msg = f"Found multiple Discord channels with the same name {channel}:" \
                + f" id {[channel.id for channel in channels]}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        else:
            channel = channels[0]

        # skip this if there is no channel and it's a dry run, which only makes sense in the
        # created channel case
        if not(channel is None and create and dry_run):
            # b/c we limited the search to guild.text_channels above
            assert isinstance(channel, discord.TextChannel), (
                f"Discord channel {channel} is NOT a TextChannel. This should not happen.")
            logger.info(f"Successfully got Discord channel {channel} with id {channel.id}")

        return channel

    async def set_channels(self) -> None:
        """
        Check that all of the Discord channels to which we want to post exist.

        If the channel exists, populate an item mapping the channel name to the channel object in
        the self.channels dict.

        If any channel does not exist, either create it, or raise a RuntimeError, depending on
        whether the config option was selected to create missing channels.
        """
        channel_names_from_export = self.parsed_messages.keys()
        logger.info("Checking that all Discord channels to which we want to post exist:"
                    f" {channel_names_from_export}")

        guild = self.get_guild_maybe_by_name(self.server_name)

        # limit search to text channels, b/c the import doesn't support voice
        # use guild.text_channels rather than self.get_all_channels() to avoid an unnecessary API call
        logger.info("All text channels on Discord server:"
                    f" {[channel.name for channel in guild.text_channels]}")

        for channel_name in channel_names_from_export:
            channel = await self.get_channel_by_name(
                guild, channel_name,
                create=self.create_channels, dry_run=self.dry_run)
            self.channels[channel_name] = channel

        logger.info("Successfully got all Discord channels to which we will be posting:"
                    f" {self.channels.keys()}")

    async def post_messages(self) -> None:
        """
        Iterate through the results of previously parsed JSON files from a Slack export, and post
        each message to Discord in the appropriate channel. Threading is preserved.

        See SlackParser.parse() for the details of the format of the parsed messages dict.

        This is the background task executed when the client runs.
        """
        logger.info("Waiting until ready")
        await self.wait_until_ready()
        logger.info(f"Ready. Begin posting all messages to all Discord channels.")
        if self.verbose:
            # This has the potential to be VERY verbose
            pprint(self.parsed_messages)

        try:
            await self.set_channels()

            for channel_name, channel_msgs_dict in self.parsed_messages.items():
                channel = self.channels[channel_name]
                await self.post_messages_to_channel(channel, channel_msgs_dict)

            # XXX maybe set a boolean to indicate success to the caller,
            #     if actual return values are hard?
            logger.info("Done posting messages to all Discord channels")
        except Exception as e:
            # Ideally this shouldn't happen
            # But when it does, esp. during development, this is helpful for debugging problems
            # XXX need to think more about error handling.
            #     should we be swallowing the exception, or passing it up,
            #     or at least in some way communicating success or failure to the caller
            logger.error(f"Caught exception posting messages: {e}")
            print_exc()
        finally:
            await self.close()

    async def post_messages_to_channel(
            self,
            channel: Optional[discord.TextChannel],
            channel_msgs_dict: dict[float,
                                    tuple[ParsedMessage,
                                          Optional[dict[float,
                                                        ParsedMessage]]]]) -> None:
        """
        This posts all of the messages of the previously parsed JSON files from a Slack export
        to a single channel.

        For threaded messages, a new thread is created at the root message, and the remaining
        messages for that thread are posted to that thread.

        Links are preserved when sending the messages to Discord.

        Files are added after sending the messages to Discord.
        """
        logger.info(f"Begin posting messages to Discord channel {channel}")

        for timestamp in sorted(channel_msgs_dict.keys()):
            (message, thread) = channel_msgs_dict[timestamp]
            sent_message = await self.send_msg_to_channel(
                channel, message.get_discord_send_kwargs())
            logger.info(f"Message posted: {timestamp}")
            if message.files:
                await self.add_files_to_message(
                    sent_message, message.get_discord_add_files_args())
                logger.info(f"{len(message.files)} files added to message")

            if thread:
                created_thread = await self.create_thread(sent_message, f"thread{timestamp}")
                for timestamp_in_thread in sorted(thread.keys()):
                    thread_message = thread[timestamp_in_thread]
                    sent_thread_message = await self.send_msg_to_thread(
                        created_thread, thread_message.get_discord_send_kwargs())
                    logger.info(f"Message in thread posted: {timestamp_in_thread}")
                    if thread_message.files:
                        await self.add_files_to_message(
                            sent_thread_message, thread_message.get_discord_add_files_args())
                        logger.info(f"{len(message.files)} files added to message in thread")

        # XXX maybe set a boolean to indicate success to the caller,
        #     if actual return values are hard?
        logger.info(f"Done posting messages to Discord channel {channel}")

    # mypy is confused and thinks there should be a self parameter in the decorator declaration
    #    slack2discord/client.py:352: error: Self argument missing for a non-static method (or an invalid type for self)
    # not sure if this is a mypy bug, there is this issue, although it claims to be fixed:
    #    https://github.com/python/mypy/issues/7778 : decorator as class member raises "self-argument missing"
    @decorator
    async def discord_retry(  # type: ignore[misc]
            coro: Callable,
            desc: str = "making discord HTTP API call",
            *args,
            **kwargs) -> None:
        """
        Wrapper around a Discord API call, with retry

        In the event of failure (e.g. getting rate limited by the server, HTTP exceptions, any
        other exceptions), will retry indefinitely until successful.

        This is not strictly the correct thing to do in all scenarios. But it's a lot more
        difficult to try to differentiate what failures should and not should not retry, so leave
        it up to the user to press Ctrl-C to manually cancel if they do not want to retry.

        It might be best to only wrap calls that are made repeatedly. If all the setup is done
        earlier, when instantiating the discord.Client, that could catch a substantial class of
        failures for which retry might not be applicable.

        Use this by wrapping a Discord API function that you wish to call, and decorating that
        function with an optional description. For example:

            @discord_retry(desc="description of call")  # type: ignore[call-arg]
            async def wrapper_func(self, discord_obj, arg1, arg2):
                await discord_obj.discord_func(arg1, arg2)

        The comment at the end of the decorator line is to suppress errors like the following
        when running the mypy static type checker:

            slack2discord/client.py:371: error: Unexpected keyword argument "desc" for "discord_retry" of "DiscordClient"

        mypy is confused by our use of parametrized decorator via the decorator module (see
        https://github.com/micheles/decorator/blob/master/docs/documentation.md#decorator-factories),
        which allows us to annotate this function with just `@decorator` and then use it below via
        @discord_retry(desc="foo"). I'm too lazy to try to figure out exactly what's going wrong
        and how to truly fix it, so for now I am just suppressing the error. Suggestions for actual
        fixes are welcome.
        """
        # seconds to wait on subsequent retries
        # not used in the rate limiting case, where the retry is explicitly provided
        retry_backoff = [1, 5, 30]

        coro_called = False
        retry_count = 0
        while not coro_called:
            try:
                ret = await coro(*args, **kwargs)
                coro_called = True
                return ret
            except Exception as e:
                retry_count += 1
                if isinstance(e, discord.RateLimited):
                    # In practice I have not been able to get this to happen (the server to return
                    # a 429), even when sending lots of messages quickly, or setting
                    # max_ratelimit_timeout (minimum 30.0) when initializing the discord
                    # client. But I can't find any code in the Python client that appears to be
                    # doing automatic rate limiting.
                    # For more details, see https://discord.com/developers/docs/topics/rate-limits
                    exc_msg = "We have been rate limited"
                    retry_sec = e.retry_after
                else:
                    if isinstance(e, discord.HTTPException):
                        exc_msg = "Caught HTTP exception"
                    else:
                        exc_msg = "Caught non-HTTP exception"
                    retry_idx = min(retry_count - 1, len(retry_backoff) - 1)
                    retry_sec = retry_backoff[retry_idx]

                logger.warning(f"{exc_msg} {desc}: {e}")
                logger.info(f"Will retry #{retry_count} after {retry_sec} seconds, press Ctrl-C to abort")
                await asyncio.sleep(retry_sec)

    @discord_retry(desc="sending message to channel")  # type: ignore[call-arg]
    async def send_msg_to_channel(
            self,
            channel: discord.TextChannel,
            send_kwargs: dict[str, Union[str, Optional[list[discord.Embed]]]]) -> Optional[discord.Message]:
        """
        Send a single message to a channel

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        if self.dry_run:
            logger.info("DRY RUN: channel.send(**kwargs)")
            return None

        # mypy doesn't like how I've declared the kwargs, ignore this for now:
        # 'No overload variant of "send" of "Messageable" matches argument type ...'
        return await channel.send(**send_kwargs)  # type: ignore[call-overload]

    @discord_retry(desc="creating thread")  # type: ignore[call-arg]
    async def create_thread(
            self,
            root_message: discord.Message,
            thread_name: str) -> Optional[discord.Thread]:
        """
        Create a thread rooted at the given message, with the given name.

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        if self.dry_run:
            logger.info(f"DRY RUN: root_message.create_thread(name={thread_name})")
            return None

        return await root_message.create_thread(name=thread_name)

    @discord_retry(desc="sending message to thread")  # type: ignore[call-arg]
    async def send_msg_to_thread(
            self,
            thread: discord.Thread,
            send_kwargs: dict[str, Union[str, Optional[list[discord.Embed]]]]) -> Optional[discord.Message]:
        """
        Send a single message to a thread

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        if self.dry_run:
            logger.info("DRY_RUN: thread.send(**kwargs)")
            return None

        # mypy doesn't like how I've declared the kwargs, ignore this for now:
        # 'No overload variant of "send" of "Messageable" matches argument type ...'
        return await thread.send(**send_kwargs)  # type: ignore[call-overload]

    @discord_retry(desc="adding files to message")  # type: ignore[call-arg]
    async def add_files_to_message(
            self,
            message: discord.Message,
            add_files_args: list[discord.File]) -> Optional[discord.Message]:
        """
        Add files to a message by uploading as attachments

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        if self.dry_run:
            logger.info("DRY_RUN: message.add_files(*add_files_args)")
            return None

        return await message.add_files(*add_files_args)
