; HW_REV == 2.0, TODO: there can be less NOPs, ICs are faster
SCLK .set 0
MOSI .set 1
MISO .set 2

.macro NOP
   MOV r23, r23
.endm

; ADS8691 - SPI-Mode-00
; -> MSB begins with falling CS
; -> begin with low CLK
; -> Reads on rising CLK-Edge
; -> transfer frame must contain 32 capture edges for writing (READING can be shorter)
; (datasheet says: "shorter frame can result in erroneous device configuration")
; (datasheet also: "host can use the short data transfer frame to read only the required number of MSB bits")

    .global adc_readwrite ; code performs with 20 MHz, ~ 1760 ns CS low
adc_readwrite:
    MOV r24, r14 ; Save input arg (CS pin)
    LDI r20, 32 ; Load Counter for outloop
    LDI r14, 0 ; Clear return reg
    CLR r30, r30, MOSI ; Set MOSI low
    CLR r30, r30, r24 ; Set CS low

adc_io_loop_head:
    SUB r20, r20, 1 ; decrement shiftloop counter
    QBBC adc_io_mosi_clr, r15, r20
adc_io_mosi_set:
    CLR r30, r30, SCLK ; Set SCLK low
    SET r30, r30, MOSI ; Set MOSI high
    JMP adc_io_loop_mid
adc_io_mosi_clr:
    CLR r30, r30, SCLK ; Set SCLK low
    CLR r30, r30, MOSI ; Set MOSI low
    NOP
adc_io_loop_mid:
    NOP
    NOP
    SET r30, r30, SCLK ; Set SCLK high
    QBBC adc_io_miso_clr, r31, MISO
adc_io_miso_set:
    SET r14, r14, r20
    QBLT adc_io_loop_head, r20, 0
    JMP adc_io_end
adc_io_miso_clr:
    NOP
    QBLT adc_io_loop_head, r20, 0

adc_io_end:
    SET r30, r30, r24 ; set CS high
    CLR r30, r30, MOSI ; Set MOSI low
    JMP r3.w2



    .global adc_fastread ; code performs with 28-33 MHz (18 bit read), ~ 550-630 ns CS low
adc_fastread:
    MOV r24, r14 ; Save input arg (CS pin)
    LDI r20, 18 ; Load Counter for loop
    LDI r14, 0 ; Clear return reg
    CLR r30, r30, MOSI ; Set MOSI low
    CLR r30, r30, r24 ; Set CS low

adc_readloop_head: ; 6 - 7 ticks, depending on input
    CLR r30, r30, SCLK ; Set SCLK low
    SUB r20, r20, 1 ; decrement shiftloop counter
    NOP
    SET r30, r30, SCLK ; Set SCLK High
    QBBC adc_readloop_tail, r31, MISO
adc_miso_set:
    SET r14, r14, r20
adc_readloop_tail:
    QBLT adc_readloop_head, r20, 0
    JMP adc_read_end

adc_nop_prepare: ; not active atm, 50 MHz (14 bit nop)
    LDI r20, 14 ; Load Counter for fast loop
adc_nop_loop:
    CLR r30, r30, SCLK ; Set SCLK low
    SUB r20, r20, 1 ; decrement shiftloop counter
    SET r30, r30, SCLK ; Set SCLK High
    QBLT adc_nop_loop, r20, 0

adc_read_end:
    SET r30, r30, r24 ; set CS high
;    CLR r30, r30, SCLK ; Set SCLK low
    JMP r3.w2



; DAC8562
; -> MSB begins with falling CS
; -> begin with high CLK
; -> Reads on falling CLK-Edge
; -> transfer frame must contain 24 capture edges for writing

    .global dac_write  ; code performs with 25 MHz, ~ 980 ns CS low
dac_write:
    LDI r20, 24 ; Load Counter for outloop
    SET r30, r30, SCLK ; Set SCLK high
    CLR r30, r30, r14 ; Set CS low

dac_loop_head:
    SUB r20, r20, 1 ; Decrement counter
    QBBS dac_mosi_set, r15, r20 ; If bit number [r20] is set in value [r15]
dac_mosi_clr:
    SET r30, r30, SCLK ; Set SCLK high
    CLR r30, r30, MOSI ; Set MOSI low
    JMP dac_loop_tail
dac_mosi_set:
    SET r30, r30, SCLK ; Set SCLK high
    SET r30, r30, MOSI ; Set MOSI high
    NOP
dac_loop_tail:
    NOP
    CLR r30, r30, SCLK ; Set SCLK low
    QBLT dac_loop_head, r20, 0

dac_end:
    NOP
    CLR r30, r30, MOSI ; clear MOSI
    SET r30, r30, r14 ; set CS high
    JMP r3.w2
