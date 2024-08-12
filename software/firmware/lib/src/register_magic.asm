
    .global get_size_in_bits
get_size_in_bits:
    LMBD r14, r14, 1 ; returns bit-position of highest valued 1, returns 32 if only 0s found
    ADD  r14, r14, 1 ; turn bit-position into bit-size
    QBNE finished, r14, 33 ; handle empty number
    AND  r14, r14, 0 ; (32+1 -> 0 bit size)
finished:
    JMP r3.w2


    .global log2safe
log2safe:
    LMBD r14, r14, 1 ; returns bit-position of highest valued 1, returns 32 if only 0s found
    QBNE fin_log, r14, 32 ; handle empty number (LMBD=32)
    AND  r14, r14, 0 ; (32 -> 0 bit size)
fin_log:
    JMP r3.w2


    .global max_value
max_value:
    MAX r14, r14, r15 ; r14 is output and first input, r15 is second input
    JMP r3.w2


    .global min_value
min_value:
    MIN r14, r14, r15 ; r14 is output and first input, r15 is second input
    JMP r3.w2
