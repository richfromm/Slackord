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
    def __init__(self, token, channel_id, parsed_messages, verbose, *args, **kwargs):
        self.token = token
        self.channel_id = channel_id
        self.parsed_messages = parsed_messages
        self.verbose = verbose

        if 'intents' not in kwargs:
            kwargs['intents'] = discord.Intents(
                messages=True,
                guilds=True)   # needed for Client.get_channel() and Client.get_all_channels()

        super().__init__(*args, **kwargs)

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

    async def post_messages(self):
        """
        Iterate through the results of previously parsing the JSON file from a Slack export and post
        each message to Discord in the channel corresponding to the given id. Threading is preserved.
        """
        logger.info("Waiting until ready")
        await self.wait_until_ready()
        logger.info(f"Ready. Posting messages to channel id {self.channel_id}")
        if self.verbose:
            pprint(self.parsed_messages)

        try:
            channel = self.get_channel(self.channel_id)
            if not channel:
                logger.error(f"Unable to get channel with id {self.channel_id}")
                logger.warn("Will NOT be able to post messages")
                return

            for timestamp in sorted(self.parsed_messages.keys()):
                (message, thread) = self.parsed_messages[timestamp]
                sent_message = await self.send_msg_to_channel(channel, message)
                logger.info(f"Message posted: {timestamp}")

                if thread:
                    created_thread = await self.create_thread(sent_message, f"thread{timestamp}")
                    for timestamp_in_thread in sorted(thread.keys()):
                        thread_message = thread[timestamp_in_thread]
                        await self.send_msg_to_thread(created_thread, thread_message)
                        logger.info(f"Message in thread posted: {timestamp_in_thread}")

            logger.info("Done posting messages")
        except Exception as e:
            # Ideally this shouldn't happen
            # But when it does, esp. during development, this is helpful for debugging problems
            logger.error(f"Caught exception posting messages: {e}")
            print_exc()
        finally:
            await self.close()

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
        return await channel.send(msg)

    @discord_retry(desc="creating thread")
    async def create_thread(self, root_message, thread_name):
        """
        Create a thread rooted at the given message, with the given name.

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        return await root_message.create_thread(name=thread_name)

    @discord_retry(desc="sending message to thread")
    async def send_msg_to_thread(self, thread, msg):
        """
        Send a single message to a thread

        In the event of failure, will retry indefinitely until successful.
        See discord_retry() docstring for more details.
        """
        return await thread.send(msg)
