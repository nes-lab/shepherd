from .sys_access import gpio_name_2_num

gpio_pin_nums: dict[str, int] = {
    "target_pwr_sel": gpio_name_2_num("P9_13"),  # gpio0[31] / 31 (deprecated naming scheme)
    "target_io_en": gpio_name_2_num("P9_12"),  # gpio1[28] / 60
    "target_io_sel": gpio_name_2_num("P9_11"),  # gpio0[30] / 30
    "en_shepherd": gpio_name_2_num("P8_13"),  # gpio0[23] / 23
    "en_harvester": gpio_name_2_num("P9_14"),  # gpio1[18] / 50
    "en_emulator": gpio_name_2_num("P9_16"),  # gpio1[19] / 51
}

# TODO: is this the same between v24 and v25?
