# CHANGES

## Current releases, on [this fork](https://github.com/richfromm/slack2discord)

### 2.5

* Add support for files attached to messages
    * Files are downloaded from Slack then uploaded to Discord and
      attached to messages
    * Add optional `--downloads-dir DOWNLOADS_DIR` command line argument
        * Defaults to a newly created dir of the form
          `./downloads/<timestamp>` relative to the location of the script.
* Get primary user information from `users.json` file, if possible
    * Previously, user information was retrieved from within each
      message. Now that is a fallback.
    * The problem was that messages with attached files do not have
      this information.
    * File is at the top level of the Slack export. Default is to
      deduce location based on other existing parameters. Can also set
      with optional `--users-file USERS_FILE` command line argument.

### 2.4

* Numerous formatting improvements
    * Fix non-standard Slack markdown syntax for **bold** and
      ~~strikethrough~~
    * Unescape HTML entities for Slack control characters (`&`, `<`,
      and `>`)
* Canonicalize directory paths specified as command line arguments
    * This fixes a bug where certain forms of the `--src-dir` option
      value caused the inferred destination channel (if not explicitly
      specified with the optional `--dest-channel` option) to not be
      properly set to the last directory in the path
    * A trailing slash (on Unix) caused the dest channel to be `None`
    * Ending with a relative path (e.g. `.` or `..`) would set that to
      the dest channel name

### 2.3

* Handle links within Slack messages
    * These are "attachments" in Slack, and "embeds" in Discord

### 2.2

* Better processing of name within Slack messages
    * Use a searchlist covering display name, real name, and user
    * This handles the bot case with no user profile
    * This fixes
      [issue#13](https://github.com/richfromm/slack2discord/issues/13)

### 2.1

* Add optional `--server SERVER` command line argument
    * This is the name of the Discord server (aka guild). This is only
      needed in the (presumably) uncommon case in which your bot is a
      member of multiple servers.
* Add the option to create missing Discord destination channels
    * Via optional `--create` command line argument
        * Creating channels requires the "Manage Channels" permission
    * The default is to still fail if a channel does not exist

### 2.0

Major refactoring, with additional functionality

* Remove GUI (tkinter)
* Rename Slackord to slack2discord
* Use Python logging
* Remove Discord bot command, use Discord client instead
    * Rather than indicating destination channel with a bot command,
      specify channel(s) by name.
    * Single channels can be specified directly on the command line,
      multiple channels can be specified via a file.
    * Support different channel names in Slack and Discord.
* Retry Discord command within inner loop of posting messages
    * With backoff
    * Includes handling HTTP 429 (Rate Limited), although in practice
      I have not yet encountered this
* Control as a command line script with args passed on command line
* Support multiple methods of invocation
    * A single export file (one day of one channel)
    * A single export dir (multiple days of one channel)
    * An entire export dir tree (multiple days of multiple channels)
* Discord token can be specified in multiple manners
    * Command line arg
    * Env var
    * Dot file

## Previous releases, from [thomasloupe/Slackord](https://github.com/thomasloupe/Slackord)

### 1.2

_Named "v1.2" upstream._

* Add support for threads

  Note that this release does **not** contain some of the threading improvements
  and fixes from [thomasloupe/Slackord#9](https://github.com/thomasloupe/Slackord/pull/9)

### 1.1

* Fix Intents requirement

### 1.0a

### 1.0

### 0.5
