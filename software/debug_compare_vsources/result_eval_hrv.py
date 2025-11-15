from itertools import product
from pathlib import Path

import pandas as pd
from config import host_selected
from config import hrv_list
from shepherd_core.logger import log
from shepherd_data import Reader

path_here = Path(__file__).parent
results: dict[str, dict[str, float]] = {}
methods = ["py_sim", "cpy_sim", "pru_emu"]

# #####################################################################
# create results               ########################################
# #####################################################################

for hrv_src, hrv_name in product(hrv_list[:1], hrv_list[1:]):
    row_: dict[str, float] = {}
    for method in methods[:2]:
        path_input = path_here / host_selected / f"hrv_{hrv_src}_{hrv_name}_{method}.h5"
        with Reader(path_input, verbose=False) as _fh:
            row_[method] = 1e3 * _fh.energy()
    results[f"{hrv_name}"] = row_

result_df = pd.DataFrame(results).transpose()
result_df["cpy-vs-py"] = 100 * (result_df["py_sim"] / result_df["cpy_sim"] - 1).abs()
result_df = result_df.reindex(["py_sim", "cpy_sim", "cpy-vs-py"], axis=1)
result_df.columns = ["PyRef/mWs", "CPy/mWs", "error/%"]
log.info(result_df.round(4).to_markdown())
