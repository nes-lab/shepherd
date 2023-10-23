"""Performance-Profiling

Shell on BBone:
sudo python3 profiler_cli.py

Options within python:
https://docs.python.org/3/library/profile.html

visualize with snakeviz:
https://jiffyclub.github.io/snakeviz/
pip install snakeviz
snakeviz cprofile.log

Alternative visualization:
https://github.com/nschloe/tuna
pip install tuna
tuna cprofile.log

Profile Import-Time (properly):
sudo python3 -X importtime -c 'from shepherd_sheep.cli import cli' 2> importtime.log
sudo python3 -X importtime -c
    'from shepherd_core.data_models.task import EmulationTask' 2> importtime.log

Timing-Optimizations:
- import EmulationTask -> from 47 s to 8.4 s
- shepherd_sheep.cli import cli -> from > 16 s to 9.7 s
- inventorize-snippet -> from > 26 s to 16 s (cProfile)

"""
import cProfile
import time
from pathlib import Path

just_import = False
path_log = Path(__file__).parent / "cprofile.log"

prof = cProfile.Profile()
time_start = time.time()

if just_import:
    prof.run("from shepherd_core.data_models.task import EmulationTask")
else:
    # NOTE: using prof.enable() & .disable() produced garbage
    prof.run(
        """
from shepherd_sheep.cli import cli
from click.testing import CliRunner
cli_runner = CliRunner()
res = cli_runner.invoke(
    cli,
    ['inventorize'],
)
    """,
    )

print(f"Routine took {time.time() - time_start} s")
prof.create_stats()
prof.dump_stats(path_log)
