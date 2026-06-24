/*
 * Copyright (C) 2016 Texas Instruments Incorporated - http://www.ti.com/
 *
 *  Redistribution and use in source and binary forms, with or without
 *  modification, are permitted provided that the following conditions
 *  are met:
 *
 *    Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *
 *    Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the
 *    distribution.
 *
 *    Neither the name of Texas Instruments Incorporated nor the names of
 *    its contributors may be used to endorse or promote products derived
 *    from this software without specific prior written permission.
 *
 *  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 *  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 *  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 *  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 *  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 *  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 *  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 *  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 *  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 *  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 *  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
*/

/*
 * This file provides routines to bring a device under JTAG control, to interface
 * with the TAP controller state machine and to read and write date from the JTAG
 * instruction and data registers via SBW. The implementation is based on code
 * provided by TI (slau320 and slaa754).
 */

#include <stdint.h>

#include "delay.h"
#include "sbw_jtag.h"
#include "sbw_transport.h"
#include "sys_gpio.h"

#define START_MAX_RETRY (5u)

void tap_reset(void)
{
    /* Check fuse */
    for (int i = 6; i > 0; i--) // 6 is nominal
    {
        tmsh_tdih();
    }
    /* JTAG FSM is now in Test-Logic-Reset, move to Run/Test Idle */
    tmsl_tdih();
}


/**
 * Shifts data into and out of the JTAG data and Instruction register.
 *
 * Assumes that the TAP controller is in Shift-DR or Shift-IR state and,
 * bit by bit, shifts data into and out of the register.
 *
 * @param format specifies length of the transfer
 * @param data data to be shifted into the register
 *
 * @returns data shifted out of the register
 *
 */
static uint32_t tap_shift(const uint16_t format, uint32_t data)
{
    uint32_t     tdo_word = 0x00000000ul;
    uint32_t     msb      = 0x00000000ul;
    uint32_t     i;

    gpio_state_t tdo;

    switch (format)
    {
        case F_BYTE: msb = 0x00000080ul; break;
        case F_WORD: msb = 0x00008000ul; break;
        case F_ADDR: msb = 0x00080000ul; break;
        case F_LONG: msb = 0x80000000ul; break;
        default: // this is an unsupported format, function will just return 0
            return tdo_word;
    }
    // shift in bits
    for (i = format; i > 0; i--)
    {
        if (i == 1) // last bit requires TMS=1; TDO one bit before TDI
        {
            tdo = ((data & msb) == 0u) ? tmsh_tdil_tdo_rd() : tmsh_tdih_tdo_rd();
        }
        else
        {
            tdo = ((data & msb) == 0u) ? tmsl_tdil_tdo_rd() : tmsl_tdih_tdo_rd();
        }
        data <<= 1;
        if (tdo) tdo_word++;
        if (i > 1) tdo_word <<= 1; // TDO could be any port pin
    }
    tmsh_tdih(); // update IR
    if (get_tclk()) tmsl_tdih();
    else tmsl_tdil();

    // de-scramble bits on a 20bit shift
    if (format == F_ADDR) { tdo_word = ((tdo_word << 16u) + (tdo_word >> 4u)) & 0x000FFFFFu; }

    return tdo_word;
}

uint32_t tap_ir_shift(uint8_t instruction)
{
    // JTAG FSM state = Run-Test/Idle
    if (get_tclk()) tmsh_tdih();
    else tmsh_tdil();

    // JTAG FSM state = Select DR-Scan
    tmsh_tdih();

    // JTAG FSM state = Select IR-Scan
    tmsl_tdih();
    // JTAG FSM state = Capture-IR
    tmsl_tdih();
    // JTAG FSM state = Shift-IR, Shift in TDI (8-bit)
    return (tap_shift(F_BYTE, instruction));
    // JTAG FSM state = Run-Test/Idle
}

uint16_t tap_dr_shift16(uint16_t data)
{
    // JTAG FSM state = Run-Test/Idle
    if (get_tclk()) tmsh_tdih();
    else tmsh_tdil();

    // JTAG FSM state = Select DR-Scan
    tmsl_tdih();
    // JTAG FSM state = Capture-DR
    tmsl_tdih();

    // JTAG FSM state = Shift-DR, Shift in TDI (16-bit)
    return (tap_shift(F_WORD, data));
    // JTAG FSM state = Run-Test/Idle
}

uint32_t tap_dr_shift20(uint32_t address)
{
    // JTAG FSM state = Run-Test/Idle
    if (get_tclk()) tmsh_tdih();
    else tmsh_tdil();

    // JTAG FSM state = Select DR-Scan
    tmsl_tdih();
    // JTAG FSM state = Capture-DR
    tmsl_tdih();

    // JTAG FSM state = Shift-DR, Shift in TDI (16-bit)
    return (tap_shift(F_ADDR, address));
    // JTAG FSM state = Run-Test/Idle
}

/* TODO: not used ATM */
int sbw_jtag_read_jmb_out(void)
{
    uint16_t sJMBINCTL;
    uint32_t lJMBOUT = 0u;
    uint16_t sJMBOUT0, sJMBOUT1;

    sJMBINCTL = 0u;

    tap_ir_shift(IR_JMB_EXCHANGE); // start exchange
    lJMBOUT = tap_dr_shift16(sJMBINCTL);

    if (lJMBOUT & OUT1RDY) // check if new data available
    {
        sJMBINCTL |= JMB32B + OUTREQ;
        //lJMBOUT  = tap_dr_shift16(sJMBINCTL); // cppcheck
        tap_dr_shift16(sJMBINCTL);
        sJMBOUT0 = (uint16_t) tap_dr_shift16(0u);
        sJMBOUT1 = (uint16_t) tap_dr_shift16(0u);
        lJMBOUT  = ((uint32_t) sJMBOUT1 << 16u) + sJMBOUT0;
    }
    return lJMBOUT;
}

int sbw_jtag_write_jmb_in16(const uint16_t data)
{
    uint16_t sJMBINCTL;
    uint16_t sJMBIN0;
    uint32_t Timeout = 0u;
    sJMBIN0          = (uint16_t) (data & 0x0000FFFFul);
    sJMBINCTL        = INREQ;

    tap_ir_shift(IR_JMB_EXCHANGE);
    do
    {
        Timeout++;
        if (Timeout >= 3000ul) { return SBW_ERR_GENERIC; }
    }
    while (!(tap_dr_shift16(0x0000u) & IN0RDY) && Timeout < 3000ul);
    if (Timeout < 3000ul)
    {
        tap_dr_shift16(sJMBINCTL);
        tap_dr_shift16(sJMBIN0);
    }
    return SBW_ERR_NONE;
}

/* TODO: not used ATM */
int sbw_jtag_write_jmb_in32(uint16_t dataX, uint16_t dataY)
{
    uint16_t sJMBINCTL;
    uint16_t sJMBIN0, sJMBIN1;
    uint32_t Timeout = 0u;

    sJMBIN0          = (uint16_t) (dataX & 0x0000FFFFul);
    sJMBIN1          = (uint16_t) (dataY & 0x0000FFFFul);
    sJMBINCTL        = JMB32B | INREQ;

    tap_ir_shift(IR_JMB_EXCHANGE);
    do
    {
        Timeout++;
        if (Timeout >= 3000ul) { return SBW_ERR_GENERIC; }
    }
    while (!(tap_dr_shift16(0x0000u) & IN0RDY) && Timeout < 3000ul);

    if (Timeout < 3000ul)
    {
        sJMBINCTL = 0x11u;
        tap_dr_shift16(sJMBINCTL);
        tap_dr_shift16(sJMBIN0);
        tap_dr_shift16(sJMBIN1);
    }
    return SBW_ERR_NONE;
}

/**
 * Enables JTAG access over SBW
 *
 * @see SLAU320AJ 2.3.1.1
 */
void sbw_entry_sequence()
{
    set_sbwtck(GPIO_STATE_LOW);
    delay_us(800ul); // delay min 800us - clr SBW controller
    set_sbwtck(GPIO_STATE_HIGH);
    delay_us(50u);

    // SpyBiWire entry sequence
    // Reset Test logic
    set_sbwtdio(GPIO_STATE_LOW); // put device in normal operation: Reset = 0
    set_sbwtck(GPIO_STATE_LOW);  // TEST pin = 0
    delay_ms(1u);                // wait 1ms (minimum: 100us)

    // SpyBiWire entry sequence
    set_sbwtdio(GPIO_STATE_HIGH); // Reset = 1
    delay_us(5u);
    set_sbwtck(GPIO_STATE_HIGH); // TEST pin = 1
    delay_us(5u);
    // initial 1 PIN_SBWTCKs to enter sbw-mode
    set_sbwtck(GPIO_STATE_LOW);
    delay_us(5u);
    set_sbwtck(GPIO_STATE_HIGH);
    delay_us(5u);
}

/* TODO: only used in magic pattern / will be removed */
void sbw_entry_sequence_rst_low()
{
    set_sbwtck(GPIO_STATE_LOW);
    set_sbwtdio(GPIO_STATE_LOW); // Added for Low RST
    delay_us(800ul);             // delay min 800us - clr SBW controller
    set_sbwtck(GPIO_STATE_HIGH);
    delay_us(50u);

    // SpyBiWire entry sequence
    // Reset Test logic
    set_sbwtdio(GPIO_STATE_LOW); // put device in normal operation: Reset = 0
    set_sbwtck(GPIO_STATE_LOW);  // TEST pin = 0
    delay_ms(1u);                // wait 1ms (minimum: 100us)

    // SpyBiWire entry sequence
    set_sbwtdio(GPIO_STATE_HIGH); // Reset = 1
    delay_us(5u);
    set_sbwtck(GPIO_STATE_HIGH); // TEST pin = 1
    delay_us(5u);
    // initial 1 PIN_SBWTCKs to enter sbw-mode
    set_sbwtck(GPIO_STATE_LOW);
    delay_us(5u);
    set_sbwtck(GPIO_STATE_HIGH);
}

int sbw_jtag_sync(void)
{
    uint32_t i = 0;

    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    tap_dr_shift16(0x1501u); // Set device into JTAG mode + read
    if ((tap_ir_shift(IR_CNTRL_SIG_CAPTURE) != JTAG_ID91) &&
        (tap_ir_shift(IR_CNTRL_SIG_CAPTURE) != JTAG_ID99) &&
        (tap_ir_shift(IR_CNTRL_SIG_CAPTURE) != JTAG_ID98))
    {
        return SBW_ERR_GENERIC;
    }
    // wait for sync
    while (!(tap_dr_shift16(0u) & 0x0200u) && i < 50u)
    {
        i++;
        delay_us(5u);
    };

    // continues if sync was successful
    if (i >= 50u) { return SBW_ERR_GENERIC; }
    return SBW_ERR_NONE;
}

/* TODO: riotee does not use this */
uint16_t magicPattern(void)
{
    uint16_t deviceJtagID = 0u;

    // Enable the JTAG interface to the device.
    sbw_jtag_connect();
    // Apply again 4wire/SBW entry Sequence.
    // set ResetPin = 0
    sbw_entry_sequence_rst_low();
    // reset TAP state machine -> Run-Test/Idle
    tap_reset();
    // feed JTAG mailbox with magic pattern
    if (sbw_jtag_write_jmb_in16(STOP_DEVICE) == SBW_ERR_NONE)
    {
        // Apply again 4wire/SBW entry Sequence.

        sbw_entry_sequence();

        tap_reset(); // reset TAP state machine -> Run-Test/Idle

        deviceJtagID = (uint16_t) tap_ir_shift(IR_CNTRL_SIG_CAPTURE);

        if (deviceJtagID == JTAG_ID91)
        {
            // if Device is in LPM.x5 -> reset IO lock of JTAG pins and Configure it
            // for debug
            tap_ir_shift(IR_TEST_3V_REG);
            tap_dr_shift16(0x4020);
        }
        else if (deviceJtagID == JTAG_ID99)
        {
            tap_ir_shift(IR_TEST_3V_REG);
            tap_dr_shift16(0x40A0);
        }
        return deviceJtagID;
    }
    return 1; // return 1 as an invalid JTAG ID
}

int sbw_jtag_connect()
{
    int retries = START_MAX_RETRY;
    do
    {
        sbw_transport_connect();
        delay_ms(15);
        sbw_entry_sequence();
        tap_reset();
        uint16_t jtag_id = (uint16_t) tap_ir_shift(IR_CNTRL_SIG_CAPTURE);
        if ((jtag_id == JTAG_ID91) || (jtag_id == JTAG_ID99) || (jtag_id == JTAG_ID98))
            return SBW_ERR_NONE;
        delay_us(500);
        sbw_transport_disconnect();
    }
    while (--retries > 0);
    return SBW_ERR_GENERIC;
}

int sbw_jtag_disconnect(void)
{
    const int rc = sbw_transport_disconnect();
    delay_ms(15u);
    return rc;
}
