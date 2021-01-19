
    .global get_left_zero_count
get_left_zero_count: ;
    LMBD r14, r14, 1 ; returns number of 0 until first 1, counting from left
    JMP r3.w2


    .global max_value
max_value:
    MAX r14, r14, r15 ; r14 is output and first input, r15 is second input
    JMP r3.w2


    .global min_value
min_value:
    MIN r14, r14, r15 ; r14 is output and first input, r15 is second input
    JMP r3.w2
