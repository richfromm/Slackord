# slack2discord

A Discord client that imports Slack-exported JSON chat history to
Discord channel(s).

## tl;dr

See [Script invocation](#script-invocation) below.

## History

This started out as
[thomasloupe/Slackord](https://github.com/thomasloupe/Slackord). I
made some contributions (see
[#7](https://github.com/thomasloupe/Slackord/pull/7) and
[#9](https://github.com/thomasloupe/Slackord/pull/9)) to add support
for threads. But then my list of additional proposed
[changes](https://github.com/thomasloupe/Slackord/issues/8) was
significant enough, that we mutually decided that me continuing
development on a hard fork would be better.

Note that there also exists a .NET version
[thomasloupe/Slackord2](https://github.com/thomasloupe/Slackord2) by the
original author, that contains additional functionality and appears to be more
actively maintained than the upstream fork from which this Python project
originates.

## Prereqs

### virtualenv

Install the following packages into a Python virtualenv:

* `discord.py` ([docs](https://discordpy.readthedocs.io/en/latest/),
[pypi](https://pypi.org/project/discord.py/),
[source](https://github.com/Rapptz/discord.py)) (_yes, there really is
a `.py` suffix included in the package name_)
* `decorator`
([docs](https://github.com/micheles/decorator/blob/master/docs/documentation.md),
[pypi](https://pypi.org/project/decorator/),
[source](https://github.com/micheles/decorator))
* `requests` ([docs](https://requests.readthedocs.io/en/latest/),
[pypi](https://pypi.org/project/requests/),
[source](https://github.com/psf/requests))

via:

    pip install discord.py decorator requests

For help creating virtual environments, see the
[venv](https://docs.python.org/3/library/venv.html) docs. If you use Python a
lot, you may also want to consider
[virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/en/latest/). If you
don't want to think much about virtual envs and just want simple Python scripts
to work, you could consider [pyv](https://github.com/richfromm/pyv).

### py3

This assumes Python 3.0. Python 2.x was EOL'd at the beginning of
2020, and no new project should be using it.

## Usage

### Slack export

To export your Slack data as JSON files, see the article at
<https://slack.com/help/articles/201658943-Export-your-workspace-data>

Note that only workspace owners/admins and org owners/admins can use this
feature. While this is available on all plans, only public channels are included
if you have the Free or Pro version. You need a Business+ or Enterprise Grid
plan to export private channels and direct messages (DMs).

I also think (but am not 100% positive) that the export has the same 90 day
limit of history imposed on Free plans as of 1 September 2022. (This change was
what motivated me to migrate from Slack to Discord and work on this tool.)

If it is a large export, this might take a while. Slack will notify you when it
is done.

The export is in the form of a zip file. Download it, and unzip it.

The contents include dirs at the top level, one for each channel. Within each
dir is one or more JSON files, of the form _`YYYY-MM-DD.json`_, one for each day
in which there are messages for that channel. Like so:

```
channel1
 |- 2022-01-01.json
 |- 2022-01-02.json
 |- ...
channel2
 |- 2022-01-01.json
 |- 2022-01-02.json
 |- ...
...
```

There is additionally some metadata contained in JSON files at the top level,
but they are not (currently) used by this script, and are not shown above.

### Discord import

#### One time setup

For complete instructions, see <https://discordpy.readthedocs.io/en/stable/discord.html>

1. Login to the Discord website and go to the Applications page:

   <https://discordapp.com/developers/applications/>

1. Create a new application. See the implications below (in creating a
   bot) of choosing an application name that contains the phrase
   "discord" (like "slack2discord").

   New Application -> Name -> **Create**

1. Optionally enter a description. For example:

   Applications -> Settings -> General Information -> Description

   > A Discord client that imports Slack-exported JSON chat history to Discord
   channel(s).

   **Save Changes**

1. Create a bot

   Applications -> Settings -> Bot -> Build-A-Bot -> **Add Bot** -> **Yes, do it!**

1. Unfortunately, if you named your App "slack2discord", Discord
   disallows the use of the phrase "discord" within a username. So
   the Username prefix (before the number) will default to
   "slack2". If you don't like that, you can choose something else:

   Applications -> Settings -> Bot -> Build-A-Bot -> Username

   like "slack2disc0rd".

1. Create a token:

   Applications -> Settings -> Bot -> Build-A-Bot -> Token -> **Reset Token** -> **Yes, do it!**

   **Copy the token now, as it will not be shown again.** This is used below.

   (Don't worry if you mess this up, you can always just repeat this step to
   create a new token.)

1. Invite the bot to your Discord server:

   Applications -> Settings -> OAuth2 -> URL Generator -> Scopes: check "**bot**"

   Bot permissions -> General permissions:

   check: "**Manage Channels**"

   Bot permissions -> Text permissions:

   additionally check: "**Send Messages**", "**Create Public Threads**", "**Send Messages in Threads**"

   This will create a URL that you can use to add the bot to your server.

    * Go to **Generated URL**
    * **Copy** the URL
    * Paste into your browser
    * Login if requested
    * Select your Discord server, and authorize the external application to
       access your Discord account, confirming the above permissions.
    * -> **Continue** -> **Authorize**
    * Do the Captcha if requested
    * Close the browser tab

#### Discord token

The Discord token (created for your bot above) must be specified in one of the
following manners. This is the order that is searched:

1. On the command line with `--token TOKEN`
1. Via the `DISCORD_TOKEN` env var
1. Via a `.discord_token` file placed in the same dir as the
   `slack2discord.py` script.

#### Script invocation

Briefly, the script is executed via:

    ./slack2discord.py [--token TOKEN] [--server SERVER] [--create] [--downloads-dir DOWNLOADS_DIR] \
        [-v | --verbose] [-n | --dry-run] <src-and-dest-related-options>

The src and dest related options can be specified in one of three different
ways:

* `--src-file SRC_FILE --dest-channel DEST_CHANNEL`

    This is for importing a single file from a Slack export, that
    corresponds to a single day of a single channel.

* `--src-dir SRC_DIR [--dest-channel DEST_CHANNEL]`

    This is for importing all of the days from a single channel in a
    Slack export, one file per day.

* `--src-dirtree SRC_DIRTREE [--channel-file CHANNEL_FILE]`

    This is for importing all of the days from multiple (potentially
    all) channels in a Slack export. One dir per channel, and within
    each channel dir, one file per day.

For more details, and complete descriptions of all command line
options, execute:

    ./slack2discord.py --help

## Internals

The Discord Python API uses
[asyncio](https://docs.python.org/3/library/asyncio.html), so there is the
potential to speed up the overall execution time by having multiple Discord HTTP
API calls execute in parallel. I have intentionally chosen to not do this.

Within a single channel, we want all of the messages in the channel (and all of
the messages within a thread) to be posted in order of timestamp, so that is a
reason to serialize those.

A better argument could be made for parallelizing posting to multiple
channels. I decided that, at least for the time being, it would be far easier to
reason about errors (and potentially restart a failed script, although no such
restart support is currently included) if only one channel was imported at a
time.

## External docs

* [Slack: How to read Slack data exports](https://slack.com/help/articles/220556107-How-to-read-Slack-data-exports)
* [Slack: Reference: Message payloads](https://api.slack.com/reference/messaging/payload)
* [Slack: Formatting text for app surfaces](https://api.slack.com/reference/surfaces/formatting)
* [discord.py: API Reference](https://discordpy.readthedocs.io/en/latest/api.html)
* [Markdown Guide: Slack](https://www.markdownguide.org/tools/slack/)
* [Markdown Guide: Discord](https://www.markdownguide.org/tools/discord/)

## Future work

Some items I am considering:

* Better error reporting, so that if an entire import is not
  successful, it is easier to resume in a way as to avoid duplicates.

* Add mypy type hints

* Add unit tests

* Ways to optimize file downloads:
    * Download multiple files asynchronously via using
      [aiohttp](https://docs.aiohttp.org/en/stable/)
    * Stream file downloads in chunks via
      [`Response.iter_content`](https://requests.readthedocs.io/en/latest/api/#requests.Response.iter_content)

Feel free to open issues in GitHub if there are any other features you
would like to see.
