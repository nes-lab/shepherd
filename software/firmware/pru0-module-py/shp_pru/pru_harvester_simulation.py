"""Simulate behavior of virtual harvester algorithms.

The simulation recreates an observer-cape and the virtual harvester
- input = hdf5-file with an ivcurve
- output = optional as hdf5-file

The output file can be analyzed and plotted with shepherds tool suite.
"""

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from .pru_harvester_model import PruHarvesterModel

patch(
    target="shepherd_core.vsource.virtual_harvester_model.VirtualHarvesterModel",
    new=PruHarvesterModel,
)
patch(target=".virtual_harvester_model.VirtualHarvesterModel", new=PruHarvesterModel)
patch(target="virtual_harvester_model.VirtualHarvesterModel", new=PruHarvesterModel)
patch(target=".VirtualHarvesterModel", new=PruHarvesterModel)
patch(target="shepherd_core.vsource.VirtualHarvesterModel", new=PruHarvesterModel)
patch(target=".vsource.VirtualHarvesterModel", new=PruHarvesterModel)
patch(target="vsource.VirtualHarvesterModel", new=PruHarvesterModel)

from shepherd_core import CalibrationHarvester
from shepherd_core import Reader
from shepherd_core import Writer
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_harvester import VirtualHarvesterConfig
from tqdm import tqdm


def simulate_harvester(
    config: VirtualHarvesterConfig, path_input: Path, path_output: Path | None = None
) -> float:
    """Simulate behavior of virtual harvester algorithms.

    Fn return the harvested energy.
    """
    # patch(target="shepherd_core.vsource.virtual_harvester_model.VirtualHarvesterModel", new=PruHarvesterModel)
    # patch(target="shepherd_core.vsource.VirtualHarvesterModel", new=PruHarvesterModel)
    #    ("shepherd_core.vsource.VirtualHarvesterModel", VirtualHarvesterModel),
    #    ("shepherd_core.vsource.virtual_harvester_model.VirtualHarvesterModel", VirtualHarvesterModel)
    # return sim_hrv_core(config, path_input, path_output)

    stack = ExitStack()
    file_inp = Reader(path_input, verbose=False)
    stack.enter_context(file_inp)
    cal_inp = file_inp.get_calibration_data()

    if path_output:
        cal_hrv = CalibrationHarvester()
        file_out = Writer(
            path_output, cal_data=cal_hrv, mode="harvester", verbose=False, force_overwrite=True
        )
        stack.enter_context(file_out)
        cal_out = file_out.get_calibration_data()
        file_out.store_hostname("hrv_sim_" + config.name)

    hrv_pru = HarvesterPRUConfig.from_vhrv(
        config,
        for_emu=True,
        dtype_in=file_inp.get_datatype(),
        window_size=file_inp.get_window_samples(),
    )
    hrv = PruHarvesterModel(hrv_pru)
    e_out_Ws = 0.0

    for _t, v_inp, i_inp in tqdm(
        file_inp.read_buffers(is_raw=True), total=file_inp.buffers_n, desc="Buffers", leave=False
    ):
        v_uV = cal_inp.voltage.raw_to_si(v_inp) * 1e6
        i_nA = cal_inp.current.raw_to_si(i_inp) * 1e9
        length = min(v_uV.size, i_nA.size)
        for _n in range(length):
            v_uV[_n], i_nA[_n] = hrv.ivcurve_sample(
                _voltage_uV=int(v_uV[_n]), _current_nA=int(i_nA[_n])
            )
        e_out_Ws += (v_uV * i_nA).sum() * 1e-15 * file_inp.sample_interval_s
        if path_output:
            v_out = cal_out.voltage.si_to_raw(v_uV / 1e6)
            i_out = cal_out.current.si_to_raw(i_nA / 1e9)
            file_out.append_iv_data_raw(_t, v_out, i_out)

    stack.close()
    return e_out_Ws
