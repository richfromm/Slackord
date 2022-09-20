import asyncio
from decorator import decorator
import logging
from pprint import pprint
from traceback import print_exc

import discord


logger = logging.getLogger(__name__)


# template copied from https://github.com/Rapptz/discord.py/blob/master/examples/background_task_asyncio.py
class DiscordClient(discord.Client):
    """
    A Discord client for the purposes of importing the content of messages exported from Slack
    *Not* intended to be generic
    """
    def __init__(self, token, parsed_messages, server_name=None,
                 verbose=False, dry_run=False,
                 **kwargs):
        self.token = token

        # see SlackParser.parse() for details
        self.parsed_messages = parsed_messages
        # name if Discord server. internally referred to as "guild".
        # optional, not needed if this client is only a member of one guild.
        self.server_name = server_name
        # a mapping of discord channel names to channel objects
        self.channels = dict()

        self.verbose = verbose
        self.dry_run = dry_run

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

    async def set_channels(self):
        """
        Check that all of the Discord channels to which we want to post exist.

        If the channel exists, populate an item mapping the channel name to the channel object in
        the self.channels dict.

        If any channel does not exist, raise an exception.
        """
        channel_names_from_export = self.parsed_messages.keys()
        logger.info("Checking that all Discord channels to which we want to post exist:"
                    f" {channel_names_from_export}")

        # use self.guilds rather than self.fetch_guilds() to avoid an unnecessary API call
        if self.server_name:
            guilds = [guild
                      for guild in self.guilds
                      if guild.name == self.server_name]
            xtra_error_str = f" with name {self.server_name}"
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

        # limit search to text channels, b/c the import doesn't support voice
        # use guild.text_channels rather than self.get_all_channels() to avoid an unnecessary API call
        logger.info("All text channels on Discord server:"
                    f" {[channel.name for channel in guild.text_channels]}")
        for channel_name in channel_names_from_export:
            channels = [channel
                        for channel in guild.text_channels
                        if channel.name == channel_name]
            if not channels:
                # XXX consider an option to support this in the future
                logger.error(f"This script will not create Discord channels that do not exist: {channel_name}")
                raise RuntimeError(f"Unable to find Discord channel {channel_name}")

            if len(channels) > 1:
                # I suspect this may not actually be possible in practice
                error_msg = f"Found multiple Discord channels with the same name {channel}: id {channel_ids}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            channel = channels[0]
            # b/c we limited the search to guild.text_channels above
            assert isinstance(channel, discord.TextChannel), (
                f"Discord channel {channel} is NOT a TextChannel. This should not happen.")
            logger.info(f"Successfully got Discord channel {channel} with id {channel.id}")

            self.channels[channel_name] = channel

        logger.info(f"Successfully got all Discord channels to which we will be posting: {self.channels.keys()}")

    async def post_messages(self):
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

    async def post_messages_to_channel(self, channel, channel_msgs_dict):
        logger.info(f"Begin posting messages to Discord channel {channel}")

        for timestamp in sorted(channel_msgs_dict.keys()):
            (message, thread) = channel_msgs_dict[timestamp]
            sent_message = await self.send_msg_to_channel(channel, message)
            logger.info(f"Message posted: {timestamp}")

            if thread:
                created_thread = await self.create_thread(sent_message, f"thread{timestamp}")
                for timestamp_in_thread in sorted(thread.keys()):
                    thread_message = thread[timestamp_in_thread]
                    await self.send_msg_to_thread(created_thread, thread_message)
                    logger.info(f"Message in thread posted: {timestamp_in_thread}")

        # XXX maybe set a boolean to indicate success to the caller,
        #     if actual return values are hard?
        logger.info(f"Done posting messages to Discord channel {channel}")

    @decorator
    async def discord_retry(coro, desc="making discord HTTP API call", *args, **kwargs):
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

            @discord_retry(desc="description of call")
            async def wrapper_func(self, discord_obj, arg1, arg2):
                await discord_obj.discord_func(arg1, arg2)

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
                    retry_sec = r1.retry_after
                else:
                    if isinstance(e, discord.HTTPException):
                        exc_msg = "Caught HTTP exception"
                    else:
                        exc_msg = "Caught non-HTTP exception"
                    retry_idx = min(retry_count - 1, len(retry_backoff) - 1)
                    retry_sec = retry_backoff[retry_idx]

                logger.warn(f"{exc_msg} {desc}: {e}")
                logger.info(f"Will retry #{retry_count} after {retry_sec} seconds, press Ctrl-C to abort")
                await asyncio.sleep(retry_sec)

    @discord_retry(desc="sending message to channel")
    async def send_msg_to_channel(self, channel, msg):
        """
        Send a single message to a channel

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        if self.dry_run:
            logger.info("DRY RUN: channel.send(msg)")
            return

        return await channel.send(msg)

    @discord_retry(desc="creating thread")
    async def create_thread(self, root_message, thread_name):
        """
        Create a thread rooted at the given message, with the given name.

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        if self.dry_run:
            logger.info(f"DRY RUN: root_message.create_thread(name={thread_name})")
            return

        return await root_message.create_thread(name=thread_name)

    @discord_retry(desc="sending message to thread")
    async def send_msg_to_thread(self, thread, msg):
        """
        Send a single message to a thread

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        if self.dry_run:
            logger.info("DRY_RUN: thread.send(msg)")
            return

        return await thread.send(msg)
