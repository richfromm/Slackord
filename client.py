import discord
import asyncio


# template copied from https://github.com/Rapptz/discord.py/blob/master/examples/background_task_asyncio.py
class Slack2DiscordClient(discord.Client):
    def __init__(self, channel_id, parsed_messages, verbose, *args, **kwargs):
        self.channel_id = channel_id
        self.parsed_messages = parsed_messages
        self.verbose = verbose
        super().__init__(*args, **kwargs)

    async def setup_hook(self) -> None:
        print("In setup_hook(), creating background task")

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
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    async def post_messages(self):
        print("Waiting until ready")
        await self.wait_until_ready()
        print(f"Ready. Posting messages to channel id {self.channel_id}")
        if self.verbose:
            pprint(parsed_messages)
        channel = self.get_channel(self.channel_id)
        if not channel:
            #logger.error(f"Unable to get channel with id {self.channel_id}")
            print(f"ERROR: Unable to get channel with id {self.channel_id}")
            await self.close()

        for timestamp in sorted(self.parsed_messages.keys()):
            (message, thread) = self.parsed_messages[timestamp]
            sent_message = await channel.send(message)
            #logger.info(f"Message posted: {timestamp}")
            print(f"Message posted: {timestamp}")

            if thread:
                created_thread = await sent_message.create_thread(name=f"thread{timestamp}")
                for timestamp_in_thread in sorted(thread.keys()):
                    thread_message = thread[timestamp_in_thread]
                    await created_thread.send(thread_message)
                    #logger.info(f"Message in thread posted: {timestamp_in_thread}")
                    print(f"Message in thread posted: {timestamp_in_thread}")

        await self.close()

        #logger.info("Done posting messages")
        print("Done posting messages")


# client = MyClient(intents=discord.Intents.default())
# client.run('token')
