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

void ResetTAP(void)
{
    // Now fuse is checked, Reset JTAG FSM
    for (int i = 6; i > 0; i--) // 6 is nominal
    {
        tmsh_tdih();
    }
    // JTAG FSM is now in Test-Logic-Reset
    tmsl_tdih(); // now in Run/Test Idle
}

int IsLockKeyProgrammed(void)
{
    uint16_t i;

    for (i = 3; i > 0; i--) //  First trial could be wrong
    {
        IR_Shift(IR_CNTRL_SIG_CAPTURE);
        if (DR_Shift16(0xAAAA) == 0x5555)
        {
            return (SC_ERR_GENERIC); // Fuse is blown
        }
    }
    return (SC_ERR_NONE); // Fuse is not blown
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
static uint32_t AllShifts(const uint16_t format, uint32_t data)
{
    uint32_t     TDOword = 0x00000000ul;
    uint32_t     MSB     = 0x00000000ul;
    uint32_t     i;

    gpio_state_t tdo;

    switch (format)
    {
        case F_BYTE: MSB = 0x00000080ul; break;
        case F_WORD: MSB = 0x00008000ul; break;
        case F_ADDR: MSB = 0x00080000ul; break;
        case F_LONG: MSB = 0x80000000ul; break;
        default: // this is an unsupported format, function will just return 0
            return TDOword;
    }
    // shift in bits
    for (i = format; i > 0; i--)
    {
        if (i == 1) // last bit requires TMS=1; TDO one bit before TDI
        {
            tdo = ((data & MSB) == 0) ? tmsh_tdil_tdo_rd() : tmsh_tdih_tdo_rd();
        }
        else { tdo = ((data & MSB) == 0) ? tmsl_tdil_tdo_rd() : tmsl_tdih_tdo_rd(); }
        data <<= 1;
        if (tdo) TDOword++;
        if (i > 1) TDOword <<= 1; // TDO could be any port pin
    }
    tmsh_tdih(); // update IR
    if (get_tclk()) { tmsl_tdih(); }
    else { tmsl_tdil(); }

    // de-scramble bits on a 20bit shift
    if (format == F_ADDR) { TDOword = ((TDOword << 16) + (TDOword >> 4)) & 0x000FFFFF; }

    return (TDOword);
}

uint32_t IR_Shift(uint8_t instruction)
{
    // JTAG FSM state = Run-Test/Idle
    if (get_tclk()) { tmsh_tdih(); }
    else { tmsh_tdil(); }
    // JTAG FSM state = Select DR-Scan
    tmsh_tdih();

    // JTAG FSM state = Select IR-Scan
    tmsl_tdih();
    // JTAG FSM state = Capture-IR
    tmsl_tdih();
    // JTAG FSM state = Shift-IR, Shift in TDI (8-bit)
    return (AllShifts(F_BYTE, instruction));
    // JTAG FSM state = Run-Test/Idle
}

uint16_t DR_Shift16(uint16_t data)
{
    // JTAG FSM state = Run-Test/Idle
    if (get_tclk()) { tmsh_tdih(); }
    else { tmsh_tdil(); }
    // JTAG FSM state = Select DR-Scan
    tmsl_tdih();
    // JTAG FSM state = Capture-DR
    tmsl_tdih();

    // JTAG FSM state = Shift-DR, Shift in TDI (16-bit)
    return (AllShifts(F_WORD, data));
    // JTAG FSM state = Run-Test/Idle
}

uint32_t DR_Shift20(uint32_t address)
{
    // JTAG FSM state = Run-Test/Idle
    if (get_tclk()) { tmsh_tdih(); }
    else { tmsh_tdil(); }
    // JTAG FSM state = Select DR-Scan
    tmsl_tdih();
    // JTAG FSM state = Capture-DR
    tmsl_tdih();

    // JTAG FSM state = Shift-DR, Shift in TDI (16-bit)
    return (AllShifts(F_ADDR, address));
    // JTAG FSM state = Run-Test/Idle
}

int i_ReadJmbOut(void)
{
    uint16_t sJMBINCTL;
    uint32_t lJMBOUT = 0u;
    uint16_t sJMBOUT0, sJMBOUT1;

    sJMBINCTL = 0u;

    IR_Shift(IR_JMB_EXCHANGE); // start exchange
    lJMBOUT = DR_Shift16(sJMBINCTL);

    if (lJMBOUT & OUT1RDY) // check if new data available
    {
        sJMBINCTL |= JMB32B + OUTREQ;
        //lJMBOUT  = DR_Shift16(sJMBINCTL); // cppcheck
        DR_Shift16(sJMBINCTL);
        sJMBOUT0 = (uint16_t) DR_Shift16(0u);
        sJMBOUT1 = (uint16_t) DR_Shift16(0u);
        lJMBOUT  = ((uint32_t) sJMBOUT1 << 16u) + sJMBOUT0;
    }
    return lJMBOUT;
}

int i_WriteJmbIn16(const uint16_t dataX)
{
    uint16_t sJMBINCTL;
    uint16_t sJMBIN0;
    uint32_t Timeout = 0u;
    sJMBIN0          = (uint16_t) (dataX & 0x0000FFFFul);
    sJMBINCTL        = INREQ;

    IR_Shift(IR_JMB_EXCHANGE);
    do {
        Timeout++;
        if (Timeout >= 3000ul) { return SC_ERR_GENERIC; }
    }
    while (!(DR_Shift16(0x0000u) & IN0RDY) && Timeout < 3000ul);
    if (Timeout < 3000ul)
    {
        DR_Shift16(sJMBINCTL);
        DR_Shift16(sJMBIN0);
    }
    return SC_ERR_NONE;
}

int i_WriteJmbIn32(uint16_t dataX, uint16_t dataY)
{
    uint16_t sJMBINCTL;
    uint16_t sJMBIN0, sJMBIN1;
    uint32_t Timeout = 0u;

    sJMBIN0          = (uint16_t) (dataX & 0x0000FFFFul);
    sJMBIN1          = (uint16_t) (dataY & 0x0000FFFFul);
    sJMBINCTL        = JMB32B | INREQ;

    IR_Shift(IR_JMB_EXCHANGE);
    do {
        Timeout++;
        if (Timeout >= 3000ul) { return SC_ERR_GENERIC; }
    }
    while (!(DR_Shift16(0x0000u) & IN0RDY) && Timeout < 3000ul);

    if (Timeout < 3000ul)
    {
        sJMBINCTL = 0x11u;
        DR_Shift16(sJMBINCTL);
        DR_Shift16(sJMBIN0);
        DR_Shift16(sJMBIN1);
    }
    return SC_ERR_NONE;
}

void EntrySequences_RstHigh_SBW()
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
}

void EntrySequences_RstLow_SBW()
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

uint16_t magicPattern(void)
{
    uint16_t deviceJtagID = 0u;

    // Enable the JTAG interface to the device.
    ConnectJTAG();
    // Apply again 4wire/SBW entry Sequence.
    // set ResetPin = 0
    EntrySequences_RstLow_SBW();
    // reset TAP state machine -> Run-Test/Idle
    ResetTAP();
    // feed JTAG mailbox with magic pattern
    if (i_WriteJmbIn16(STOP_DEVICE) == SC_ERR_NONE)
    {
        // Apply again 4wire/SBW entry Sequence.

        EntrySequences_RstHigh_SBW();

        ResetTAP(); // reset TAP state machine -> Run-Test/Idle

        deviceJtagID = (uint16_t) IR_Shift(IR_CNTRL_SIG_CAPTURE);

        if (deviceJtagID == JTAG_ID91)
        {
            // if Device is in LPM.x5 -> reset IO lock of JTAG pins and Configure it
            // for debug
            IR_Shift(IR_TEST_3V_REG);
            DR_Shift16(0x4020);
        }
        else if (deviceJtagID == JTAG_ID99)
        {
            IR_Shift(IR_TEST_3V_REG);
            DR_Shift16(0x40A0);
        }
        return deviceJtagID;
    }
    return 1; // return 1 as an invalid JTAG ID
}

void ConnectJTAG()
{
    sbw_transport_connect();
    delay_ms(15u);
}

void StopJtag(void)
{
    sbw_transport_disconnect();
    delay_ms(15u);
}
