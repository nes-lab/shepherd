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
 * This file provides device-level access to MSP430FR devices via SBW. The implementation
 * is based on code provided by TI (slau320 and slaa754).
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

#include "delay.h"

#include "device.h"
#include "sbw_jtag.h"
#include "sbw_transport.h"

#define ACTIVATE_MAGIC_PATTERN
#define DISABLE_JTAG_SIGNATURE_WRITE 1
#define MAX_ENTRY_TRY                7

#define FR4xx_LOCKREGISTER           0x160
#define SAFE_FRAM_PC                 0x0004

#define FRAM_LOW                     0xC400
#define FRAM_HIGH                    0xFFFF

#define JTAG_SIGNATURE_LOW           0xFF80
#define JTAG_SIGNATURE_HIGH          0xFF88

typedef struct
{
    uint16_t device_id;
    uint16_t core_id;
    uint16_t jtag_id;
    uint32_t device_id_ptr;
} dev_dsc_t;

/**
 * Loads a given address into the target CPU's program counter (PC).
 *
 * @param Addr destination address
 *
 */
static void SetPC_430Xv2(uint32_t Addr)
{
    uint16_t Mova;
    uint16_t Pc_l;

    Mova = 0x0080;
    Mova += (uint16_t) ((Addr >> 8) & 0x00000F00);
    Pc_l = (uint16_t) ((Addr & 0xFFFF));

    // Check Full-Emulation-State at the beginning
    IR_Shift(IR_CNTRL_SIG_CAPTURE);
    if (DR_Shift16(0) & 0x0301)
    {
        // MOVA #imm20, PC
        clr_tclk_sbw();
        // take over bus control during clock LOW phase
        IR_Shift(IR_DATA_16BIT);
        set_tclk_sbw();
        DR_Shift16(Mova);
        // insert on 24.03.2010 Florian
        clr_tclk_sbw();
        // above is just for delay
        IR_Shift(IR_CNTRL_SIG_16BIT);
        DR_Shift16(0x1400);
        IR_Shift(IR_DATA_16BIT);
        clr_tclk_sbw();
        set_tclk_sbw();
        DR_Shift16(Pc_l);
        clr_tclk_sbw();
        set_tclk_sbw();
        DR_Shift16(0x4303);
        clr_tclk_sbw();
        IR_Shift(IR_ADDR_CAPTURE);
        DR_Shift20(0x00000);
    }
}

/**
 * Writes one byte/uint16_t at a given address ( <0xA00)
 *
 * @param Format F_BYTE or F_WORD
 * @param Addr Address of data to be written
 * @param Data Data to be written
 */
static int WriteMem_430Xv2(uint16_t Format, uint32_t Addr, uint16_t Data)
{
    // Check Init State at the beginning
    IR_Shift(IR_CNTRL_SIG_CAPTURE);
    if (!(DR_Shift16(0) & 0x0301)) return SC_ERR_GENERIC;

    clr_tclk_sbw();
    IR_Shift(IR_CNTRL_SIG_16BIT);
    if (Format == F_WORD) { DR_Shift16(0x0500); }
    else { DR_Shift16(0x0510); }
    IR_Shift(IR_ADDR_16BIT);
    DR_Shift20(Addr);

    set_tclk_sbw();
    // New style: Only apply data during clock high phase
    IR_Shift(IR_DATA_TO_ADDR);
    DR_Shift16(Data); // Shift in 16 bits
    clr_tclk_sbw();
    IR_Shift(IR_CNTRL_SIG_16BIT);
    DR_Shift16(0x0501);
    set_tclk_sbw();
    // one or more cycle, so CPU is driving correct MAB
    clr_tclk_sbw();
    set_tclk_sbw();
    // Processor is now again in Init State

    return SC_ERR_NONE;
}

/**
 * Reads one byte/word from a given address in memory
 *
 * @param Format F_BYTE or F_WORD
 * @param Addr Address of data to be written
 *
 * @returns Data from device
 */
uint16_t ReadMem_430Xv2(uint16_t Format, uint32_t Addr)
{
    uint16_t TDOword = 0;
    delay_ms(1);
    // Check Init State at the beginning
    IR_Shift(IR_CNTRL_SIG_CAPTURE);
    if (DR_Shift16(0) & 0x0301)
    {
        // Read Memory
        clr_tclk_sbw();
        IR_Shift(IR_CNTRL_SIG_16BIT);
        if (Format == F_WORD)
        {
            DR_Shift16(0x0501); // Set uint16_t read
        }
        else
        {
            DR_Shift16(0x0511); // Set byte read
        }
        IR_Shift(IR_ADDR_16BIT);
        DR_Shift20(Addr); // Set address
        IR_Shift(IR_DATA_TO_ADDR);
        set_tclk_sbw();
        clr_tclk_sbw();
        TDOword = DR_Shift16(0x0000); // Shift out 16 bits

        set_tclk_sbw();
        // one or more cycle, so CPU is driving correct MAB
        clr_tclk_sbw();
        set_tclk_sbw();
        // Processor is now again in Init State
    }
    return TDOword;
}

/**
 * Execute a Power-On Reset (POR) using JTAG CNTRL SIG register
 *
 * @returns SC_ERR_NONE if target is in Full-Emulation-State afterwards, SC_ERR_GENERIC otherwise
 */
static int ExecutePOR_430Xv2(void)
{
    // provide one clock cycle to empty the pipe
    clr_tclk_sbw();
    set_tclk_sbw();

    // prepare access to the JTAG CNTRL SIG register
    IR_Shift(IR_CNTRL_SIG_16BIT);
    // release CPUSUSP signal and apply POR signal
    DR_Shift16(0x0C01);
    // release POR signal again
    DR_Shift16(0x0401);

    // Set PC to 'safe' memory location
    IR_Shift(IR_DATA_16BIT);
    clr_tclk_sbw();
    set_tclk_sbw();
    clr_tclk_sbw();
    set_tclk_sbw();
    DR_Shift16(SAFE_FRAM_PC);
    // PC is set to 0x4 - MAB value can be 0x6 or 0x8

    // drive safe address into PC
    clr_tclk_sbw();
    set_tclk_sbw();

    IR_Shift(IR_DATA_CAPTURE);

    // two more to release CPU internal POR delay signals
    clr_tclk_sbw();
    set_tclk_sbw();
    clr_tclk_sbw();
    set_tclk_sbw();

    // now set CPUSUSP signal again
    IR_Shift(IR_CNTRL_SIG_16BIT);
    DR_Shift16(0x0501);
    // and provide one more clock
    clr_tclk_sbw();
    set_tclk_sbw();
    // the CPU is now in 'Full-Emulation-State'

    // disable Watchdog Timer on target device now by setting the HOLD signal
    // in the WDT_CNTRL register
    uint16_t id = IR_Shift(IR_CNTRL_SIG_CAPTURE);
    if (id == JTAG_ID98) { WriteMem_430Xv2(F_WORD, 0x01CC, 0x5A80); }
    else { WriteMem_430Xv2(F_WORD, 0x015C, 0x5A80); }

    // Initialize Test Memory with default values to ensure consistency
    // between PC value and MAB (MAB is +2 after sync)
    if (id == JTAG_ID91 || id == JTAG_ID99)
    {
        WriteMem_430Xv2(F_WORD, 0x06, 0x3FFF);
        WriteMem_430Xv2(F_WORD, 0x08, 0x3FFF);
    }

    // Check if device is in Full-Emulation-State again and return status
    IR_Shift(IR_CNTRL_SIG_CAPTURE);
    if (DR_Shift16(0) & 0x0301) { return (SC_ERR_NONE); }

    return (SC_ERR_GENERIC);
}

/**
 * Resync the JTAG connection and execute a Power-On-Reset
 *
 * @returns SC_ERR_NONE if operation was successful, SC_ERR_GENERIC otherwise
 *
 */
static int SyncJtag_AssertPor(void)
{
    int i = 0;

    IR_Shift(IR_CNTRL_SIG_16BIT);
    DR_Shift16(0x1501); // Set device into JTAG mode + read

    if ((IR_Shift(IR_CNTRL_SIG_CAPTURE) != JTAG_ID91) &&
        (IR_Shift(IR_CNTRL_SIG_CAPTURE) != JTAG_ID99) &&
        (IR_Shift(IR_CNTRL_SIG_CAPTURE) != JTAG_ID98))
    {
        return (SC_ERR_GENERIC);
    }
    // wait for sync
    while (!(DR_Shift16(0) & 0x0200) && i < 50) { i++; };
    // continues if sync was successful
    if (i >= 50) { return (SC_ERR_GENERIC); }
    // execute a Power-On-Reset
    if (ExecutePOR_430Xv2() != SC_ERR_NONE) { return (SC_ERR_GENERIC); }

    return (SC_ERR_NONE);
}

/**
 * Determine & compare core identification info
 *
 * @param jtag_id pointer where jtag id is stored
 *
 * @returns SC_ERR_NONE if correct JTAG ID was returned, SC_ERR_GENERIC otherwise
 */
static int GetJtagID(uint16_t *jtag_id)
{
    // uint16_t JtagId = 0;  //initialize JtagId with an invalid value
    int i;
    for (i = 0; i < MAX_ENTRY_TRY; i++)
    {
        // release JTAG/TEST signals to safely reset the test logic
        StopJtag();
        // establish the physical connection to the JTAG interface
        ConnectJTAG();
        // Apply again 4wire/SBW entry Sequence.
        // set ResetPin =1

        EntrySequences_RstHigh_SBW();
        // reset TAP state machine -> Run-Test/Idle
        ResetTAP();
        // shift out JTAG ID
        *jtag_id = (uint16_t) IR_Shift(IR_CNTRL_SIG_CAPTURE);
        delay_us(500);
        // break if a valid JTAG ID is being returned
        if ((*jtag_id == JTAG_ID91) || (*jtag_id == JTAG_ID99) ||
            (*jtag_id == JTAG_ID98)) //****************************
        {
            break;
        }
    }

    if (i >= MAX_ENTRY_TRY)
    {
        // if connected device is MSP4305438 JTAG Mailbox is not usable
#ifdef ACTIVATE_MAGIC_PATTERN
        for (i = 0; i < MAX_ENTRY_TRY; i++)
        {
            // if no JTAG ID is returns -> apply magic pattern to stop user cd
            // execution
            *jtag_id = magicPattern();
            if ((*jtag_id == 1) || (i >= MAX_ENTRY_TRY))
            {
                // if magic pattern failed and 4 tries passed -> return status error
                return (SC_ERR_GENERIC);
            }
            else { break; }
        }
        // For MSP430F5438 family mailbox is not functional in reset state.
        // Because of this issue the magicPattern is not usable on MSP430F5438
        // family devices
#else
        return (SC_ERR_ET_DCDC_DEVID);
#endif
    }
    if ((*jtag_id == JTAG_ID91) || (*jtag_id == JTAG_ID99) || (*jtag_id == JTAG_ID98))
    {
        return (SC_ERR_NONE);
    }
    else { return (SC_ERR_ET_DCDC_DEVID); }
}

/**
 * Determine & compare core identification info (Xv2)
 *
 * @param core_id pointer where core id gets stored
 * @param device_id_ptr pointer where device id pointer gets stored
 *
 * @returns STATUS_OK if correct JTAG ID was returned, STATUS_ERROR otherwise
 */
static int GetCoreipIdXv2(uint16_t *core_id, uint32_t *device_id_ptr)
{
    IR_Shift(IR_COREIP_ID);
    *core_id = DR_Shift16(0);
    if (*core_id == 0) { return (SC_ERR_GENERIC); }
    IR_Shift(IR_DEVICE_ID);
    *device_id_ptr = DR_Shift20(0);
    // The ID pointer is an un-scrambled 20bit value
    return (SC_ERR_NONE);
}

/**
 * Takes target device under JTAG control. Disables the target watchdog.
 * Reads device information.
 *
 * @param dsc pointer where device info gets stored
 *
 * @returns SC_ERR_GENERIC if fuse is blown, incorrect JTAG ID or synchronizing time-out; SC_ERR_NONE otherwise
 */
static int GetDevice_430Xv2(dev_dsc_t *dsc)
{
    if (GetJtagID(&dsc->jtag_id) != SC_ERR_NONE) { return SC_ERR_GENERIC; }
    if (IsLockKeyProgrammed() != SC_ERR_NONE) // Stop here if fuse is already blown
    {
        return STATUS_FUSEBLOWN;
    }
    if (GetCoreipIdXv2(&dsc->core_id, &dsc->device_id_ptr) != SC_ERR_NONE)
    {
        return SC_ERR_GENERIC;
    }
    if (SyncJtag_AssertPor() != SC_ERR_NONE) { return SC_ERR_GENERIC; }
    // CPU is now in Full-Emulation-State
    // read DeviceId from memory
    dsc->device_id = ReadMem_430Xv2(F_WORD, dsc->device_id_ptr + 4);

    return (SC_ERR_NONE);
}

/**
 * Release the target device from JTAG control
 *
 * @param Addr 0xFFFE: Perform Reset, means Load Reset Vector into PC, otherwise: Load Addr into PC
 */
static int ReleaseDevice_430Xv2(uint32_t Addr)
{
    uint16_t shiftResult = 0;
    switch (Addr)
    {
        case V_BOR:

            // perform a BOR via JTAG - we loose control of the device then...
            shiftResult = IR_Shift(IR_TEST_REG);
            DR_Shift16(0x0200);
            delay_ms(5); // wait some time before doing any other action
            // JTAG control is lost now - GetDevice() needs to be called again to gain
            // control.
            break;

        case V_RESET:

            IR_Shift(IR_CNTRL_SIG_16BIT);
            DR_Shift16(0x0C01); // Perform a reset
            DR_Shift16(0x0401);
            shiftResult = IR_Shift(IR_CNTRL_SIG_RELEASE);
            break;

        default:

            SetPC_430Xv2(Addr); // Set target CPU's PC
            // prepare release & release
            set_tclk_sbw();
            IR_Shift(IR_CNTRL_SIG_16BIT);
            DR_Shift16(0x0401);
            IR_Shift(IR_ADDR_CAPTURE);
            shiftResult = IR_Shift(IR_CNTRL_SIG_RELEASE);
    }

    if ((shiftResult == JTAG_ID91) || (shiftResult == JTAG_ID99) ||
        (shiftResult == JTAG_ID98)) //****************************
    {
        return (SC_ERR_NONE);
    }
    else { return (SC_ERR_GENERIC); }
}

/**
 * Disables the Memory Protection Unit (FRAM devices only)
 *
 * @returns SC_ERR_NONE if MPU was disabled successfully, SC_ERR_GENERIC otherwise
 */
static int DisableMpu_430Xv2(void)
{
    if (IR_Shift(IR_CNTRL_SIG_CAPTURE) == JTAG_ID98)
    {
        uint16_t newRegisterVal = ReadMem_430Xv2(F_WORD, FR4xx_LOCKREGISTER);
        newRegisterVal &= ~0xFF03;
        newRegisterVal |= 0xA500;
        // unlock MPU for FR4xx/FR2xx
        WriteMem_430Xv2(F_WORD, FR4xx_LOCKREGISTER, newRegisterVal);
        if ((ReadMem_430Xv2(F_WORD, FR4xx_LOCKREGISTER) & 0x3) == 0x0) { return SC_ERR_NONE; }
        return SC_ERR_GENERIC;
    }
    else
    {
        uint16_t MPUCTL0    = 0x0000;
        uint16_t FramCtlKey = 0xA500;

        // first read out the MPU control register 0
        MPUCTL0             = ReadMem_430Xv2(F_WORD, 0x05A0);

        // check MPUENA bit: if MPU is not enabled just return no error
        if ((MPUCTL0 & 0x1) == 0) { return (SC_ERR_NONE); }
        // check MPULOCK bit: if MPULOCK is set write access to all MPU
        // registers is disabled until a POR/BOR occurs
        if ((MPUCTL0 & 0x3) != 0x1)
        {
            // feed in magic pattern to stop code execution after BOR
            if (i_WriteJmbIn16(STOP_DEVICE) == SC_ERR_GENERIC) { return (SC_ERR_GENERIC); }
            // Apply BOR to reset the device
            set_sbwtck(GPIO_STATE_HIGH);
            delay_ms(20);
            set_sbwtck(GPIO_STATE_LOW);

            set_sbwtdio(GPIO_STATE_HIGH);
            delay_ms(20);
            set_sbwtdio(GPIO_STATE_LOW);
            delay_ms(20);

            // connect to device again, apply entry sequence
            ConnectJTAG();

            // Apply again 4wire/SBW entry Sequence.

            EntrySequences_RstHigh_SBW();

            // reset TAP state machine -> Run-Test/Idle
            ResetTAP();
            // get jtag control back
            if (SC_ERR_GENERIC == SyncJtag_AssertPor()) { return (SC_ERR_GENERIC); }
        }
        // MPU Registers are unlocked. MPU can now be disabled.
        // Set MPUENA = 0, write Fram MPUCTL0 key
        WriteMem_430Xv2(F_WORD, 0x05A0, FramCtlKey);

        MPUCTL0 = ReadMem_430Xv2(F_WORD, 0x05A0);
        // now check if MPU is disabled
        if ((MPUCTL0 & 0x1) == 0) { return SC_ERR_NONE; }
        return SC_ERR_GENERIC;
    }
}

/* Disables access to and communication with the MSP430. After this, the core should be reset and running */
static int close()
{
    ReleaseDevice_430Xv2(V_RESET);
    sbw_transport_disconnect();
    return DRV_ERR_OK;
}

/**
 * Prepares the MSP430FR for access.
 *
 * @param pin_swdclk pin number for SBWTCK signal. Note: Only supports pins of GPIO port 0.
 * @param pin_swdio pin number for SBWTDIO signal. Note: Only supports pins of GPIO port 0.
 * @param f_clk frequency of SBWTCK signal
 *
 * @returns DRV_ERR_OK on success
 */
static int open(unsigned int pin_sbwtck, unsigned int pin_sbwtdio, unsigned int f_clk)
{
    dev_dsc_t dsc;
    sbw_transport_init(pin_sbwtck, pin_sbwtdio, f_clk);
    sbw_transport_connect();

    if (GetDevice_430Xv2(&dsc) != SC_ERR_NONE) return DRV_ERR_GENERIC;

    /* Disables FRAM write protection */
    if (DisableMpu_430Xv2() != SC_ERR_NONE)
    {
        close();
        return DRV_ERR_GENERIC;
    }

    return DRV_ERR_OK;
}

/**
 * Writes a word to the target memory
 *
 * @param target memory address
 * @param data word to be written
 *
 */
static int write(uint32_t address, uint32_t data)
{
#if DISABLE_JTAG_SIGNATURE_WRITE
    /* Prevent write to JTAG signature region -> this would disable JTAG access */
    if ((address >= JTAG_SIGNATURE_LOW) && (address < JTAG_SIGNATURE_HIGH))
    {
        return DRV_ERR_PROTECTED;
    }
#endif
    if (WriteMem_430Xv2(F_WORD, (uint16_t) address, (uint16_t) data) != 0) return DRV_ERR_GENERIC;
    return DRV_ERR_OK;
}

/**
 * Reads a word from the specified address in memory.
 *
 * @param dst pointer to destination
 * @param addr target memory address
 */
static int read(uint32_t *dst, uint32_t address)
{
    *dst = (uint32_t) ReadMem_430Xv2(F_WORD, (uint16_t) address);
    return DRV_ERR_OK;
}

/**
 * Verifies a word at the specified address in memory.
 *
 * @param addr target memory address
 * @param data expected memory content
 */
static int verify(uint32_t address, uint32_t data)
{
    uint16_t read_back = ReadMem_430Xv2(F_WORD, (uint16_t) address);

    if ((data & 0xFFFF) == read_back) return DRV_ERR_OK;
    else return DRV_ERR_VERIFY;
}

/* Emulates a flash erase by sequentially setting memory to 1s */
static int erase()
{
    /* No real erase on FRAM -> emulate FLASH erase */
    for (unsigned int address = FRAM_LOW; address < FRAM_HIGH; address += 2)
    {
        int ret = write(address, 0xFFFF);

        if ((ret != DRV_ERR_OK) && (ret != DRV_ERR_PROTECTED)) return DRV_ERR_GENERIC;
    }
    return DRV_ERR_OK;
}

/* FRAM doesn't need erase before write -> just ignore function call */
static int      dummy_erase() { return DRV_ERR_OK; }

device_driver_t msp430fr_driver = {
        .open             = open,
        .erase            = dummy_erase,
        .write            = write,
        .read             = read,
        .verify           = verify,
        .close            = close,
        .word_width_bytes = 2,
};
