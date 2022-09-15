from argparse import ArgumentParser, RawDescriptionHelpFormatter
import logging
from sys import argv, exit
from textwrap import dedent


logger = logging.getLogger(__name__)


DESCRIPTION = dedent(
    """
    slack2discord parses data exported from Slack, and imports it to Discord.
    """)

# XXX TO DO:
# - token will be optional, if not cmd line optino, then env var or dot file
# - consider adding the ability for the script to create channels
USAGE = dedent(
    f"""
    {argv[0]} --token TOKEN [-v | --verbose] [-n | --dry-run] <src-and-test-related-options>

    src and dest related options must follow one of the following mutually exclusive formats:

        --src_file SRC_FILE --dest_channel DEST_CHANNEL

            This is for importing a single file from a Slack export, that corresponds to a single
            day of a single channel. Both the src file and the dest Discord channel are required.

        --src_dir SRC_DIR [--dest_channel DEST_CHANNEL]

            This is for importing all of the days from a single channel in a Slack export, one file
            per day.  The Slack channel name can be inferred from the name of the src dir. The dest
            Discord channel is optional; if not present, it defaults to the same name as the src
            Slack channel.

        --src_dirtree SRC_DIRTREE [--channel_file CHANNEL_FILE]

            This is for importing all of the days from multiple (potentially all) channels in a
            Slack export. One dir per channel, and within each channel dir, one file per day. The
            src dir tree is the top level of the unzip'd Slack export. If the channel file is not
            given, all channels in the Slack export (all subdirs) are imported to Discord, and the
            channel names are the same as in Slack.

            A channel file can be used to limit the channels imported, and/or to change the names
            of channels. Each line in the file corresponds to a single channel to import. If only
            one name is specified, this is the name of the channel in both Slack and Discord. If
            two whitespace-separated names are included, those correspond to the src Slack channel
            name and the dest Discord channel name respectively.

    Slack and Discord channel names should **not** include the leading pound sign (#)

    dest Discord channels must already exist. This script will not create channels, it will only
    post to existing channels.
    """)

EPILOG = dedent(
    """
    Prior to running this script, you must create a slack2discord application in your Discord and
    create a token at:
        https://discordapp.com/developers/applications/

    To export your Slack data (so that it can be imported to Discord with this script), see:
        https://slack.com/help/articles/201658943-Export-your-workspace-data
    """)

def exit_usage(msg):
    """
    Exit with a specific error message, plus the usage, if the specific config is not legal.
    """
    logger.error(msg)
    print(USAGE)
    exit(1)


def check_config(config):
    """
    Check that the config is legal.

    Mutually exclusive ways of running the script (see USAGE above) make this a bit more
    complicated than simply required vs. optional args.
    """
    # These are all mutually exclusive
    one_file = config.src_file is not None
    one_channel = config.src_dir is not None
    multi_channels = config.src_dirtree is not None

    ways = int(one_file) + int(one_channel) + int(multi_channels)
    if ways > 1:
        exit_usage("--src_file (one file), --src_dir (one channel), --src_dirtree (multiple channels)"
                   " are all mutually exclusive")
    if ways == 0:
        exit_usage("One (and only one) of --src_file (one file), --src_dir (one channel), or"
                    "--src_dirtree (multiple channels) is required")

    if one_file and config.dest_channel is None:
        exit_usage("--dest_channel is required with --src_file (one file)")

    if multi_channels and config.dest_channel is not None:
        exit_usage("--dest_channel is not allowed with --src_dirtree (multiple channels)."
                   " It is only allowed with --src_file (one file) or --src_dir (one channel)")

    if config.channel_file and not multi_channels:
        exit_usage("--channel_file is only allowed with --src_dirtree (multiple channels)."
                   " It is not allowed with --src_file (one file) or --src_dir (one channel)")


def get_config(argv):
    """
    Parse args and return the config.
    """

    parser = ArgumentParser(formatter_class=RawDescriptionHelpFormatter,
                            description=DESCRIPTION, epilog=EPILOG, usage=USAGE)

    # XXX this will eventually be optional
    #     searchlist will be: cmd line option, DISCORD_TOKEN env var, .discord_token file in dir of script
    parser.add_argument('--token',
                        required=True,
                        help="Discord token. Obtain from the Discord GUI when setting up your"
                        " application at https://discordapp.com/developers/applications/")

    parser.add_argument('--src_file',
                        required=False,
                        default=None,
                        help="Single source file for import from Slack (from one day of one"
                        " channel)")

    parser.add_argument('--dest_channel',
                        required=False,
                        default=None,
                        help="Destination Discord channel (if only migrating one channel)")

    parser.add_argument('--src_dir',
                        required=False,
                        default=None,
                        help="Directory of source files for import from Slack (for all days from"
                        " one channel)")

    parser.add_argument('--src_dirtree',
                        required=False,
                        default=None,
                        help="Directory tree of source directories for import from Slack (from all"
                        " channels). This is the top level of the unzip'd Slack export.")

    parser.add_argument('--channel_file',
                        required=False,
                        default=None,
                        help="File containing list of Slack channels to port to Discord, with"
                        " optional mapping to Discord channels if named differently.")

    parser.add_argument('-v', '--verbose',
                        required=False,
                        action='store_true')

    parser.add_argument('-n', '--dry_run',
                        required=False,
                        action='store_true')

    config = parser.parse_args()
    check_config(config)
    return config
