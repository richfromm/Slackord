# CHANGES

## Current releases, on [this fork](https://github.com/richfromm/slack2discord)

### 2.0

Major refactoring, with additional functionality

* Remove tkinter
* Rename Slackord to slack2discord
* Use Python logging
* Remove Discord bot command, use Discord client instead
    * Rather than indicating destination channel with a bot command,
      specify channel(s) by name.
    * Single channels can be specified directly on the command line,
      multiple channels can be specified via a file.
    * Support different channel names in Slack and Discord.
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