from itertools import product
from pathlib import Path

import pandas as pd
from config import emu_hrv_list
from config import emu_src_list
from config import host_selected
from shepherd_core.logger import log
from shepherd_data import Reader

path_here = Path(__file__).parent
results: dict[str, dict[str, float]] = {}
methods = ["py_sim", "cpy_sim", "pru_emu"]

# #####################################################################
# create results               ########################################
# #####################################################################

for hrv_name, src_name in product(emu_hrv_list, emu_src_list):
    row_: dict[str, float] = {}
    for method in methods:
        path_input = path_here / host_selected / f"hrv_{hrv_name}_{src_name}_{method}.h5"
        with Reader(path_input, verbose=False) as _fh:
            row_[method] = 1e3 * _fh.energy()
    results[f"{hrv_name} to {src_name}"] = row_

result_df = pd.DataFrame(results).transpose()
result_df["cpy-vs-py"] = 100 * (result_df["py_sim"] / result_df["cpy_sim"] - 1).abs()
result_df["pru-vs-py"] = 100 * (result_df["py_sim"] / result_df["pru_emu"] - 1).abs()
result_df = result_df.reindex(["py_sim", "cpy_sim", "cpy-vs-py", "pru_emu", "pru-vs-py"], axis=1)
result_df.columns = ["PyRef/mWs", "CPy/mWs", "error/%", "Pru/mWs", "error/%"]
log.info(result_df.round(3).to_markdown())
