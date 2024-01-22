from pathlib import Path

import pandas as pd
from sync_analysis import LogicTrace
from sync_analysis import LogicTraces
from sync_analysis import logger

path_here = Path(__file__).parent / "05_rpi_cm4"
save_pickle = False

ltraces = LogicTraces(path_here, glitch_ns=20)
_stat: dict[str, list] = {
    "diff": [],
    "rising": [],
    "low": [],
}

for trace in ltraces.traces:  # TODO: transform into CLI
    if save_pickle:
        trace.to_file(path_here)

    for _ch in range(trace.channel_count):
        _data_r = trace.calc_durations_ns(_ch, edge_a_rising=True, edge_b_rising=True)
        _expt = trace.calc_expected_value(_data_r, mode_log10=True)
        _name = trace.name + f"_ch{_ch}_rising_{round(_expt / 1e6)}ms"
        _data_r[:, 1] = _data_r[:, 1] - _expt
        trace.plot_series_jitter(_data_r, _name, path_here)
        _stat["rising"].append(trace.get_statistics(_data_r, _name))

        _data_l = trace.calc_durations_ns(_ch, edge_a_rising=False, edge_b_rising=True)
        _name = trace.name + f"_ch{_ch}_low"
        _stat["low"].append(trace.get_statistics(_data_l, _name))

    # sync between channels
    for _ch1 in range(trace.channel_count):
        _data1 = trace.get_edge_timestamps(_ch1, rising=True)
        for _ch2 in range(_ch1 + 1, trace.channel_count):
            _data2 = trace.get_edge_timestamps(_ch2, rising=True)
            _diff = trace.calc_duration_free_ns(_data1, _data2)
            _name = trace.name + f"_diff_{_ch1}u{_ch2}"
            trace.plot_series_jitter(_diff, _name, path_here)
            _stat["diff"].append(trace.get_statistics(_diff, _name))

# ltraces.plot_comparison_series(start=0)
_stat_df = {
    _k: pd.DataFrame(_v, columns=LogicTrace.get_statistics_header()) for _k, _v in _stat.items()
}
for _k, _v in _stat_df.items():
    logger.info("")
    logger.info("TYPE: %s", _k)
    logger.info(_v.to_string())

chosen = ["002_", "014_", "034_", "042_"]
ltraces.traces = [trace for trace in ltraces.traces if trace.name[:4] in chosen]
ltraces.plot_comparison_series(start=0)

# Trigger-Experiment:
# - watch P8_19-low variance under load (currently 29.3 - 49.3 us)
#   - busy wait is 50 us, this should not be close to 0
#   - example: [ 29348 <| 43416 || 46416 || 48726 |> 49276 ]
# - watch P8_19-rising
#   - example: [ -662 <| -404 || -142 || 128 |> 378 ]
