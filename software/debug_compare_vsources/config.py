from shepherd_core.vsource import ResistiveTarget

# Observer to run tests on

host_selected = "sheep0"

# HARVEST

hrv_list = [
    "ivcurve",
    "cv10",
    "cv20",
    "mppt_voc",
    "mppt_bq_solar",
    "mppt_bq_thermoelectric",
    "mppt_po",
    "mppt_opt",
]

# EMULATION

emu_hrv_list = [
    "ivcurve",
    "mppt_voc",
    "mppt_po",
]

emu_src_list = [
    "direct",
    "dio_cap",
    "BQ25504",
    "BQ25570",
]

emu_target = ResistiveTarget(R_Ohm=1000)
