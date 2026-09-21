from periphery import GPIO
from periphery import GPIOError
from shepherd_sheep.sys_access import get_gpio_info
from shepherd_sheep.sys_access import gpio_name_2_num

gpio_v25: dict[str, str] = {
    # sheep cape io
    "target_pwr_sel": "P9_13",  # gpio0[31] / 31 (deprecated scheme)
    "target_io_en": "P9_12",  # gpio1[28] / 60
    "target_io_sel": "P9_11",  # gpio0[30] / 30
    "en_shepherd": "P8_13",  # gpio0[23] / 23
    "en_harvester": "P9_14",  # gpio1[18] / 50
    "en_emulator": "P9_16",  # gpio1[19] / 51
    # eeprom
    "wp_pin": "P9_23",
    # target io v25
    "dirA": "P8_37",
    "dirB": "P8_38",
    "dirC": "P9_14",
    "dir_prg1": "P8_31",
    "dir_prg2": "P8_32",  # TODO: rest of GPIO?
    # launcher
    "button": "P8_18",  # GPIO65 (deprecated naming scheme)
    "led": "P8_19",  # GPIO22 (deprecated naming scheme)
    # watchdog
    "wdt_ack": "P8_10",
}

gpio_data = get_gpio_info()
for gpio_name, gpio_value in gpio_v25.items():
    gpio_num = gpio_name_2_num(gpio_value)
    gpio_dsc = gpio_data[gpio_num]
    print(f"Trying {gpio_value} / {gpio_num}: {gpio_dsc}")
    try:
        gpio = GPIO(gpio_num + 512, "in")
        gpio.close()
    except GPIOError:
        print("\t failed during export")
    # /sys/class/gpio/
    # echo 18 > /sys/class/gpio/chip0/export -> works
    # offset by 512?
    # echo 618 > /sys/class/gpio/export
