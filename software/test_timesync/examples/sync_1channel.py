from pathlib import Path

import numpy as np
from sync_analysis import LogicTrace
from sync_analysis import LogicTraces
from sync_analysis import logger

path_here = Path(__file__).parent

lt = LogicTraces(path_here)
_dtrans: dict[str, dict[str, np.ndarray]] = {
    "low": {},
    "rising": {},
}
for trace in lt.traces:
    trace.to_file(path_here)
    trace.analyze_inter_jitter(rising=True)
    for _ch in range(trace.channel_count):
        _data = trace.calc_durations_ns(_ch, edge_a_rising=True, edge_b_rising=True)
        _name = trace.name + f"_ch{_ch}"
        _expt = trace.calc_expected_value(_data)
        trace.plot_series_jitter(_data - _expt, trace.data[_ch], _name, path_here)
        _dtrans["rising"][_name] = trace.calc_durations_ns(_ch, edge_a_rising=True, edge_b_rising=True) - _expt
        _dtrans["low"][_name] = trace.calc_durations_ns(_ch, edge_a_rising=False, edge_b_rising=True)
lt.plot_comparison_series(start=0)
lt.plot_comparison_series(start=2)
for _state, _ddict in _dtrans.items():
    logger.info("State: %s", _state)
    header = True
    for _name, _data in _ddict.items():
        LogicTrace.analyze_series_jitter(_data, _name, with_header=header)
        header = False

# Trigger-Experiment:
# - watch P8_19-low variance under load (currently 29.3 - 49.3 us)
#   - busy wait is 50 us, this should not be close to 0
#   - example: [ 29348 <| 43416 || 46416 || 48726 |> 49276 ]
# - watch P8_19-rising
#   - example: [ -662 <| -404 || -142 || 128 |> 378 ]

