
    .global gpio_read_pin
gpio_read_pin:
    QBBS pin_is_set, r31, r14
pin_is_clear:
    LDI r14, 0
    JMP r3.w2
pin_is_set:
    LDI r14, 1
    JMP r3.w2


    .global gpio_toggle_pin
gpio_toggle_pin:
    QBBS gpio_clear_pin, r31, r14 ;

    .global gpio_set_pin
gpio_set_pin:
    SET r30, r30, r14 ; set pin high
    JMP r3.w2

    .global gpio_clear_pin
gpio_clear_pin:
    CLR r30, r30, r14 ; set pin low
    JMP r3.w2
