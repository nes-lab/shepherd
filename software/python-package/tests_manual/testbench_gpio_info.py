
from shepherd_sheep.sys_access import get_gpio_info
from shepherd_sheep.sys_access import gpio_name_2_num

gpio_v25: list[str] = [
    "P8_10",
    "P8_11",
    "P8_12",
    "P8_13",
    "P8_14",
    "P8_15",
    "P8_16",
    "P8_17",
    "P8_18",
    "P8_19",
    "P8_26",
    "P8_27",
    "P8_28",
    "P8_29",
    "P8_30",
    "P8_31",
    "P8_32",
    "P8_33",
    "P8_34",
    "P8_35",
    "P8_36",
    "P8_37",
    "P8_38",
    "P8_39",
    "P8_40",
    "P8_41",
    "P8_42",
    "P8_43",
    "P8_44",
    "P8_45",
    "P8_46",
    "P9_11",
    "P9_12",
    "P9_13",
    "P9_14",
    "P9_16",
    "P9_17",
    "P9_18",
    "P9_23",
    "P9_25",
    "P9_27",
    "P9_28",
    "P9_29",
    "P9_30",
    "P9_31",
    "P9_41B",
    "P9_42B",
    # "P9_24",
    # "P9_26",
]

gpio_data = get_gpio_info()
for gpio_value in gpio_v25:
    gpio_num = gpio_name_2_num(gpio_value)
    gpio_dsc = gpio_data[gpio_num]
    if "unused" not in gpio_dsc:
        print(f"Problem {gpio_value} / {gpio_num}: {gpio_dsc}")
