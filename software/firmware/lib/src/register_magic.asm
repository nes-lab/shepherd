
    .global get_left_zero_count
get_left_zero_count: ;
    LMBD r14, r14, 1 ; returns number of 0 until first 1, counting from left
    JMP r3.w2
