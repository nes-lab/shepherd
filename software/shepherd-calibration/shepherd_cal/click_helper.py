import click


def group_options(*options):
    def wrapper(function):
        for option in reversed(options):
            function = option(function)
        return function

    return wrapper


# TODO: switch to this unifying style for all shepherd-tools
# common general shepherd options

opt_version = click.version_option()

# common click-options used for shepherd cal
# use with decorator: @group_options(opt_optionname)

opt_user = click.option("--user", "-u", type=str, default="jane", help="Host Username")
opt_password = click.option(
    "--password",
    "-p",
    type=str,
    default=None,
    help="Host User Password -> only needed when key-credentials are missing",
)

opt_smu_ip = click.option(
    "--smu-ip", type=str, default="192.168.1.108", help="IP of SMU-Device in network"
)

opt_harvester = click.option(
    "--harvester", "-h", is_flag=True, help="only handle harvester"
)
opt_emulator = click.option(
    "--emulator", "-e", is_flag=True, help="only handle emulator"
)

opt_smu_2wire = click.option(
    "--smu-2wire",
    is_flag=True,
    help="don't use 4wire-mode for measuring voltage (NOT recommended)",
)
opt_smu_nplc = click.option(
    "--smu-nplc",
    type=float,
    default=16,
    help="measurement duration in pwrline cycles (.001 to 25, but > 18 can cause error-msgs)",
)
