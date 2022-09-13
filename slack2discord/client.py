import asyncio
from decorator import decorator
#from functools import wraps
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
        self.retry_count = 0

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
                # XXX to help test failures, slow this down
                logger.info("XXX Waiting 1 sec to slow things down for testing failures")
                await asyncio.sleep(1)
                (message, thread) = self.parsed_messages[timestamp]
                sent_message = await self.send_msg(channel, message)
                #sent_message = self.send_msg(channel, message)
                logger.info(f"Message posted: {timestamp}")

                if thread:
                    created_thread = await sent_message.create_thread(name=f"thread{timestamp}")
                    for timestamp_in_thread in sorted(thread.keys()):
                        # XXX to help test failures, slow this down
                        logger.info("XXX Waiting 1 sec to slow things down for testing failures")
                        await asyncio.sleep(1)
                        thread_message = thread[timestamp_in_thread]
                        await created_thread.send(thread_message)
                        logger.info(f"Message in thread posted: {timestamp_in_thread}")

            logger.info("Done posting messages")
        except Exception as e:
            # Ideally this shouldn't happen
            # But when it does, esp. during development, this is helpful for debugging problems
            logger.error(f"Caught exception posting messages: {e}")
            print_exc()
        finally:
            await self.close()

    # def discord_retry(self, f):
    #     """
    #     Decorator to retry a function in the discord API that makes an HTTP request to the
    #     discord server.

    #     Use by annotating a method with `@discord_retry`
    #     """
    #     logger.info("XXX begin discord_retry()")
    #     async def wrapper(self, *args, **kwargs):
    #         logger.info("XXX begin wrapper()")
    #         async def retry(log_msg, retry_sec):
    #             logger.info("XXX begin retry()")
    #             self.retry_count += 1
    #             logger.warn(log_msg)
    #             logger.info(f"Will retry #{self.retry_count} after {retry_sec} seconds, press Ctrl-C to abort")
    #             await asyncio.sleep(retry_sec)
    #             logger.info("XXX end retry()")

    #         message_sent = False
    #         self.retry_count = 0
    #         while not message_sent:
    #             try:
    #                 # XXX should we put await here ?
    #                 f(*args, **kwargs)
    #                 message_sent = True
    #             except discord.RateLimited as rl:
    #                 # In practice I have not been able to get this to happen (the server to return a
    #                 # 429), even when sending lots of messages quickly, or setting
    #                 # max_ratelimit_timeout (minimum 30.0) when initializing the discord client. But I
    #                 # can't find any code in the Python client that appears to be doing automatic rate
    #                 # limiting.
    #                 # For more details, see https://discord.com/developers/docs/topics/rate-limits
    #                 await retry(f"We have been rate limited sending message: {rl}", r1.retry_after)
    #             except discord.HTTPException as he:
    #                 await retry(f"Caught HTTP exception sending message: {he}", 5)
    #             except Exception as e:
    #                 await retry(f"Caught non-HTTP exception sending message: {e}", 5)
    #         logger.info("XXX end wrapper()")

    #     logger.info("XXX end discord_retry()")
    #     return wrapper

    # @discord_retry
    # async def send_msg(self, channel, msg):
    #     logger.info("XXX begin send_message")
    #     await channel.send(msg)
    #     logger.info("XXX end send_message")

    # async def discord_retry(self, f, *args, **kwargs):
    #     """
    #     Decorator to retry a function in the discord API that makes an HTTP request to the
    #     discord server.

    #     Use by annotating a method with `@discord_retry`
    #     """
    #     logger.info("XXX begin discord_retry()")
    #     logger.info(f"f={f} args={args} kwargs={kwargs}")
    #     async def retry(log_msg, retry_sec):
    #         logger.info("XXX begin retry()")
    #         self.retry_count += 1
    #         logger.warn(log_msg)
    #         logger.info(f"Will retry #{self.retry_count} after {retry_sec} seconds, press Ctrl-C to abort")
    #         await asyncio.sleep(retry_sec)
    #         logger.info("XXX end retry()")

    #     message_sent = False
    #     self.retry_count = 0
    #     while not message_sent:
    #         try:
    #             # XXX should we put await here ?
    #             f(*args, **kwargs)
    #             message_sent = True
    #         except discord.RateLimited as rl:
    #             # In practice I have not been able to get this to happen (the server to return a
    #             # 429), even when sending lots of messages quickly, or setting
    #             # max_ratelimit_timeout (minimum 30.0) when initializing the discord client. But I
    #             # can't find any code in the Python client that appears to be doing automatic rate
    #             # limiting.
    #             # For more details, see https://discord.com/developers/docs/topics/rate-limits
    #             await retry(f"We have been rate limited sending message: {rl}", r1.retry_after)
    #         except discord.HTTPException as he:
    #             await retry(f"Caught HTTP exception sending message: {he}", 5)
    #         except Exception as e:
    #             await retry(f"Caught non-HTTP exception sending message: {e}", 5)

    #     logger.info("XXX end discord_retry()")

    # def discord_retry(*args, **kwargs):
    #     logger.info(f"XXX begin discord_retry(), args={args} kwargs={kwargs}")
    #     def wrapper(func, *args, **kwargs):
    #         logger.info(f"XXX begin wrapper, func={func} args={args} kwargs={kwargs}")
    #         @wraps(func)
    #         async def wrapped(*args, **kwargs):
    #             logger.info(f"XXX begin wrapped, func={func} args={args} kwargs={kwargs}")
    #             # return await func(*args, **kwargs)
    #             ret = await func(*args, **kwargs)
    #             logger.info("XXX end wrapped")
    #             return ret
    #         logger.info(f"XXX end wrapper")
    #         return wrapped
    #     logger.info("XXX end discord_retry()")
    #     return wrapper

    @decorator
    async def discord_retry(coro, *args, **kwargs):
        logger.info(f"XXX begin discord_retry(), args={args} kwargs={kwargs}")
        ret = await coro(*args, **kwargs)
        logger.info("XXX end discord_retry()")
        return ret

    # @discord_retry
    # async def send_msg(self, channel, msg):
    #     logger.info(f"XXX begin send_message, channel={channel} msg={msg}")
    #     await self.discord_retry(channel.send(msg))
    #     logger.info("XXX end send_message")

    @discord_retry
    async def send_msg(self, channel, msg):
        logger.info(f"XXX begin send_message, channel={channel} msg={msg}")
        await channel.send(msg)
        logger.info("XXX end send_message")

    # async def send_msg(self, channel, msg):
    #     """
    #     Send a single message to a channel

    #     In the event of failure (e.g. getting rate limited by the server, HTTP exceptions, any
    #     other exceptions), will retry indefinitely until successful.

    #     This is not strictly the correct thing to do in all scenarios. But it's a lot more
    #     difficult to try to differentiate what failures should and not should not retry, so leave
    #     it up to the user to press Ctrl-C to manually cancel if they do not want to retry.

    #     Additionally, it is hoped that a substantial class of failures would have been caught
    #     earlier (e.g. when instantiating the discord.Client), before we get to send_msg().
    #     """
    #     async def retry(log_msg, retry_sec):
    #         self.retry_count += 1
    #         logger.warn(log_msg)
    #         logger.info(f"Will retry #{self.retry_count} after {retry_sec} seconds, press Ctrl-C to abort")
    #         await asyncio.sleep(retry_sec)

    #     message_sent = False
    #     self.retry_count = 0
    #     while not message_sent:
    #         try:
    #             await channel.send(msg)
    #             message_sent = True
    #         except discord.RateLimited as rl:
    #             # In practice I have not been able to get this to happen (the server to return a
    #             # 429), even when sending lots of messages quickly, or setting
    #             # max_ratelimit_timeout (minimum 30.0) when initializing the discord client. But I
    #             # can't find any code in the Python client that appears to be doing automatic rate
    #             # limiting.
    #             # For more details, see https://discord.com/developers/docs/topics/rate-limits
    #             await retry(f"We have been rate limited sending message: {rl}", r1.retry_after)
    #         except discord.HTTPException as he:
    #             await retry(f"Caught HTTP exception sending message: {he}", 5)
    #         except Exception as e:
    #             await retry(f"Caught non-HTTP exception sending message: {e}", 5)
