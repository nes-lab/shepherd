"""Alternative to sampling real data from harvester

This only tests the emulation-tool-chain from virtual harvesting and all major virtual sources.

Input data is the jogging-dataset from the shepherd-tools.
"""

from pathlib import Path
from urllib.request import urlretrieve

from shepherd_core.data_models.content import VirtualHarvesterConfig
from shepherd_core.logger import log
from shepherd_core.vsource import simulate_harvester
from shepherd_data import ivonne

sim_duration = 32
file_url = "https://github.com/nes-lab/shepherd-tools/raw/refs/heads/main/shepherd_data/examples/jogging_10m.iv"
path_root = Path(__file__).parent / "sheep0"
file_ivonne = path_root / "jogging_10m.iv"
file_ivcurve = path_root / "hrv_ivcurve.h5"

hrv_list = [
    "mppt_voc",
    "mppt_po",
]

if not file_ivonne.exists():
    log.info("Input-IV-File not found - will download it")
    urlretrieve(file_url, file_ivonne)

# convert IVonne to IVCurve
if not file_ivcurve.exists():
    log.info("Input-IVCurve-File not found - will download it")
    with ivonne.Reader(file_ivonne) as db:
        db.convert_2_ivsurface(file_ivcurve, duration_s=sim_duration)

# Simulated harvest
for hrv_name in hrv_list:
    file_output = path_root / f"hrv_{hrv_name}.h5"
    if file_output.exists():
        log.info("Output-File file '%s' already exists, will skip!", file_output.name)

    E_out_Ws = simulate_harvester(
        config=VirtualHarvesterConfig(name=hrv_name),
        path_input=file_ivcurve,
        path_output=file_output,
    )
    log.info("E_out = %.3f mWs -> %s", E_out_Ws * 1e3, hrv_name)
