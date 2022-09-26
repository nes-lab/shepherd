    .global __delay_var_cycles
__delay_var_cycles:
    SUB r14, r14, 2
    QBLT __delay_var_cycles, r14, 1
    JMP r3.w2
