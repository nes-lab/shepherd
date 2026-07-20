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

/*
    This driver was made more generic by adding changes done in Riotee
    - https://github.com/orgua/Riotee_ProbeFirmware/tree/main/firmware/src
    - the last remaining specialization is DisableMpu_430Xv2() & erase_fn()
        -

    Removed some specialized FNs:
    - GetDevice_430Xv2 -> partly replaced by sbw_dev_connect()
    - setPC_.. -> sbw_dev_pc_set()
    - ReleaseDevice -> sbw_dev_release
    - GetJtagID (based on magic pattern)
    - (jtag) magic pattern
*/

#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

#include "delay.h"

#include "device.h"
#include "sbw_jtag.h"
#include "sbw_transport.h"

#define DISABLE_JTAG_SIGNATURE_WRITE (1u)

#define FR4xx_LOCKREGISTER           (0x160u)
#define SAFE_FRAM_PC                 (0x0004u)

#define FRAM_LOW                     (0xC400u)
#define FRAM_HIGH                    (0xFFFFu)

#define JTAG_SIGNATURE_LOW           (0xFF80u)
#define JTAG_SIGNATURE_HIGH          (0xFF88u)

/**
 * Checks if device is protected from JTAG access
 *
 * @returns true if locked, else false
 *
 * @see SLAU320AJ 2.4.3
 */
static bool is_lock_key_programmed(void)
{
    uint16_t i;

    for (i = 3; i > 0; i--) //  First trial could be wrong
    {
        tap_ir_shift(IR_CNTRL_SIG_CAPTURE);
        if (tap_dr_shift16(0xAAAAu) == 0x5555u)
        {
            return true; // Fuse is blown
        }
    }
    return false; // Fuse is not blown
}

/**
 * Reads one byte/word from a given address in memory
 *
 * @param addr Address of data to be written
 *
 * @returns Data from device
 */
static int mem_read_word(uint16_t *dst, uint32_t addr)
{
    // Check Init State at the beginning
    tap_ir_shift(IR_CNTRL_SIG_CAPTURE);
    if (!(tap_dr_shift16(0u) & 0x0301u)) return SBW_ERR_GENERIC;

    // Read Memory
    clr_tclk_sbw();
    /* enables setting of the complete JTAG control signal register with the
    * next 16-bit JTAG data access.*/
    tap_ir_shift(IR_CNTRL_SIG_16BIT);

    tap_dr_shift16(0x0501u); // x501 for word, x511 for byte (read)

    tap_ir_shift(IR_ADDR_16BIT);
    tap_dr_shift20(addr); // Set address
    tap_ir_shift(IR_DATA_TO_ADDR);
    set_tclk_sbw();
    clr_tclk_sbw();
    *dst = tap_dr_shift16(0x0000u); // Shift out 16 bits

    set_tclk_sbw();
    // one or more cycle, so CPU is driving correct MAB
    clr_tclk_sbw();
    set_tclk_sbw();
    // Processor is now again in Init State

    return SBW_SUCCESS;
}

/**
 * Writes one byte/uint16_t at a given address ( <0xA00)
 *
 * @param addr Address of data to be written
 * @param data data to be written
 */
static int mem_write_word(uint32_t addr, uint16_t data)
{
    // Check Init State at the beginning
    tap_ir_shift(IR_CNTRL_SIG_CAPTURE);
    if (!(tap_dr_shift16(0u) & 0x0301u)) return SBW_ERR_GENERIC;

    clr_tclk_sbw();
    tap_ir_shift(IR_CNTRL_SIG_16BIT);

    tap_dr_shift16(0x0500u); // x500 for word, x510 for byte (write)
    tap_ir_shift(IR_ADDR_16BIT);
    tap_dr_shift20(addr);

    set_tclk_sbw();
    // New style: Only apply data during clock high phase
    tap_ir_shift(IR_DATA_TO_ADDR);
    tap_dr_shift16(data); // Shift in 16 bits
    clr_tclk_sbw();
    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    tap_dr_shift16(0x0501u);
    set_tclk_sbw();
    // one or more cycle, so CPU is driving correct MAB
    clr_tclk_sbw();
    set_tclk_sbw();
    // Processor is now again in Init State

    return SBW_SUCCESS;
}


/**
 * Execute a Power-On Reset (POR) using JTAG CNTRL SIG register
 *
 * @returns SBW_SUCCESS if target is in Full-Emulation-State afterwards, SBW_ERR_GENERIC otherwise
 *
 * @see SLAU320AJ 2.3.2.2.3
 */
static int sbw_dev_reset(void)
{
    // provide one clock cycle to empty the pipe
    clr_tclk_sbw();
    set_tclk_sbw();

    // prepare access to the JTAG CNTRL SIG register
    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    // release CPUSUSP signal and apply POR signal
    tap_dr_shift16(0x0C01u);
    // release POR signal again
    tap_dr_shift16(0x0401u);

    // Set PC to 'safe' memory location
    tap_ir_shift(IR_DATA_16BIT);
    clr_tclk_sbw();
    set_tclk_sbw();
    clr_tclk_sbw();
    set_tclk_sbw();
    tap_dr_shift16(SAFE_FRAM_PC);
    // PC is set to 0x4 - MAB value can be 0x6 or 0x8

    // drive safe address into PC
    clr_tclk_sbw();
    set_tclk_sbw();

    tap_ir_shift(IR_DATA_CAPTURE);

    // two more to release CPU internal POR delay signals
    clr_tclk_sbw();
    set_tclk_sbw();
    clr_tclk_sbw();
    set_tclk_sbw();

    // now set CPUSUSP signal again
    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    tap_dr_shift16(0x0501u);
    // and provide one more clock
    clr_tclk_sbw();
    set_tclk_sbw();
    // the CPU is now in 'Full-Emulation-State'

    // disable Watchdog Timer on target device now by setting the HOLD signal
    // in the WDT_CNTRL register
    const uint16_t id = tap_ir_shift(IR_CNTRL_SIG_CAPTURE);
    if (id == JTAG_ID98) mem_write_word(0x01CCu, 0x5A80u);
    else mem_write_word(0x015Cu, 0x5A80u);

    // Initialize Test Memory with default values to ensure consistency
    // between PC value and MAB (MAB is +2 after sync)
    if (id == JTAG_ID91 || id == JTAG_ID99)
    {
        mem_write_word(0x06u, 0x3FFFu);
        mem_write_word(0x08u, 0x3FFFu);
    }

    // Check if device is in Full-Emulation-State again and return status
    tap_ir_shift(IR_CNTRL_SIG_CAPTURE);
    if (tap_dr_shift16(0u) & 0x0301u) return SBW_SUCCESS;

    return SBW_ERR_GENERIC;
}

/**
 * Loads a value into a CPU register
 *
 * @param reg register number
 * @param data data to load
 *
 * @see SLAU320AJ 2.3.2.2.2
 */
int sbw_dev_reg_set(uint8_t reg, uint32_t data)
{
    uint16_t Mova;
    uint16_t data_lower;

    /* MOVA #imm20, PC, see SLAUF391F 1.6.1*/
    Mova = 0x0080u | reg;
    Mova += (uint16_t) ((data >> 8u) & 0x00000F00u);
    data_lower = (uint16_t) ((data & 0xFFFFu));

    // Check Full-Emulation-State at the beginning
    tap_ir_shift(IR_CNTRL_SIG_CAPTURE);
    if (!(tap_dr_shift16(0u) & 0x0301u)) return SBW_ERR_GENERIC;

    clr_tclk_sbw();
    // take over bus control during clock LOW phase
    tap_ir_shift(IR_DATA_16BIT);
    set_tclk_sbw();
    tap_dr_shift16(Mova);
    clr_tclk_sbw();
    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    tap_dr_shift16(0x1400u); // Release low byte
    tap_ir_shift(IR_DATA_16BIT);
    clr_tclk_sbw();
    set_tclk_sbw();
    tap_dr_shift16(data_lower);
    clr_tclk_sbw();
    set_tclk_sbw();
    tap_dr_shift16(0x4303u); // insert NOP
    clr_tclk_sbw();
    tap_ir_shift(IR_ADDR_CAPTURE);
    tap_dr_shift20(0x00000u);
    return SBW_SUCCESS;
}

/**
 * Loads an address into the PC register
 *
 * @param addr address to load
 *
 * @see SLAU320AJ 2.3.2.2.2
 */
int sbw_dev_pc_set(uint32_t addr)
{
    sbw_dev_reg_set(0u, addr);
    return SBW_SUCCESS;
}

/**
 * Brings CPU to halt
 *
 * @see SLAU320AJ 2.3.2.1.4
 */
int sbw_dev_halt(void)
{
    /* Set to instruction fetch mode */
    tap_ir_shift(IR_DATA_16BIT);
    tap_dr_shift16(0x3FFF); // JMP $+0

    clr_tclk_sbw();

    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    tap_dr_shift16(0x2409); // set JTAG_HALT bit
    set_tclk_sbw();
    return SBW_SUCCESS;
}

/**
 * Releases CPU from halt and continues execution
 *
 * @see SLAU320AJ 2.3.2.1.4
 */
int sbw_dev_release(void)
{
    clr_tclk_sbw();

    // debugstr("Releasing target MSP430.");

    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    tap_dr_shift16(0x2C01);
    tap_dr_shift16(0x2401); // Release reset.
    tap_ir_shift(IR_CNTRL_SIG_RELEASE);
    set_tclk_sbw();
    return SBW_SUCCESS;
}


/**
 * Determine & compare core identification info (Xv2)
 *
 * @param core_id pointer where core id gets stored
 *
 * @returns STATUS_OK if correct JTAG ID was returned, STATUS_ERROR otherwise
 */
int sbw_dev_get_coreip_id(uint16_t *coreip_id)
{
    tap_ir_shift(IR_COREIP_ID);
    *coreip_id = tap_dr_shift16(0u);
    if (*coreip_id == 0u) { return SBW_ERR_GENERIC; }

    // The ID pointer is an un-scrambled 20bit value
    return SBW_SUCCESS;
}

int sbw_dev_get_device_id_ptr(uint32_t *device_id_ptr)
{
    tap_ir_shift(IR_DEVICE_ID);
    // The ID pointer is an un-scrambled 20bit value
    *device_id_ptr = tap_dr_shift20(0u);
    return SBW_SUCCESS;
}

// TODO: not used ATM
int sbw_dev_get_device_id(uint16_t *device_id)
{
    int      rc;
    uint32_t device_id_ptr;

    if ((rc = sbw_dev_get_device_id_ptr(&device_id_ptr)) != SBW_SUCCESS) return rc;
    if ((rc = sbw_jtag_sync()) != SBW_SUCCESS) return rc;
    if ((rc = sbw_dev_reset()) != SBW_SUCCESS) return rc;

    // CPU is now in Full-Emulation-State
    // read DeviceId from memory
    if ((rc = mem_read_word(device_id, device_id_ptr + 4)) != SBW_SUCCESS)
    {
        return rc; // TODO: ERR_READ_DEVICE_ID
    }
    return SBW_SUCCESS;
}


/**
 * Disables the Memory Protection Unit (FRAM devices only)
 *
 * @returns SBW_SUCCESS if MPU was disabled successfully, SBW_ERR_GENERIC otherwise
 */
static int DisableMpu_430Xv2(void)
{
    if (tap_ir_shift(IR_CNTRL_SIG_CAPTURE) == JTAG_ID98)
    {
        uint16_t newRegisterVal;
        mem_read_word(&newRegisterVal, FR4xx_LOCKREGISTER);
        newRegisterVal &= ~0xFF03u;
        newRegisterVal |= 0xA500u;
        // unlock MPU for FR4xx/FR2xx
        mem_write_word(FR4xx_LOCKREGISTER, newRegisterVal);
        mem_read_word(&newRegisterVal, FR4xx_LOCKREGISTER);
        if ((newRegisterVal & 0x3u) == 0x0u) { return SBW_SUCCESS; }
        return SBW_ERR_GENERIC;
    }
    else // TODO: make OP safer by checking for additional IDs?
    {
        uint16_t MPUCTL0    = 0x0000u;
        uint16_t FramCtlKey = 0xA500u;

        // first read out the MPU control register 0
        mem_read_word(&MPUCTL0, 0x05A0u);

        // check MPUENA bit: if MPU is not enabled just return no error
        if ((MPUCTL0 & 0x1u) == 0u) { return SBW_SUCCESS; }
        // check MPULOCK bit: if MPULOCK is set write access to all MPU
        // registers is disabled until a POR/BOR occurs
        if ((MPUCTL0 & 0x3u) != 0x1u)
        {
            // feed in magic pattern to stop code execution after BOR
            if (sbw_jtag_write_jmb_in16(STOP_DEVICE) == SBW_ERR_GENERIC) { return SBW_ERR_GENERIC; }
            // Apply BOR to reset the device
            set_sbwtck(GPIO_STATE_HIGH);
            delay_ms(20u);
            set_sbwtck(GPIO_STATE_LOW);

            set_sbwtdio(GPIO_STATE_HIGH);
            delay_ms(20u);
            set_sbwtdio(GPIO_STATE_LOW);
            delay_ms(20u);

            // connect to device again, apply entry sequence
            sbw_jtag_connect();

            // Apply again 4wire/SBW entry Sequence.

            sbw_entry_sequence();

            // reset TAP state machine -> Run-Test/Idle
            tap_reset();
            // get jtag control back
            if (sbw_jtag_sync() != SBW_SUCCESS) { return SBW_ERR_GENERIC; }
            // TODO: add POR here - was included in sync before
        }
        // MPU Registers are unlocked. MPU can now be disabled.
        // Set MPUENA = 0, write Fram MPUCTL0 key
        mem_write_word(0x05A0u, FramCtlKey);

        mem_read_word(&MPUCTL0, 0x05A0u);
        // now check if MPU is disabled
        if ((MPUCTL0 & 0x1u) == 0u) { return SBW_SUCCESS; }
        return SBW_ERR_GENERIC;
    }
}

/* Disables access to and communication with the MSP430. After this, the core should be reset and running */
static int sbw_dev_disconnect()
{
    tap_ir_shift(IR_CNTRL_SIG_16BIT);
    tap_dr_shift16(0x2C01);
    tap_dr_shift16(0x2401);
    tap_ir_shift(IR_CNTRL_SIG_RELEASE);
    const int rc = sbw_jtag_disconnect();
    return rc;
}

/**
 * Prepares the MSP430FR for access.
 *
 * @param pin_swdclk pin number for SBWTCK signal. Note: Only supports pins of GPIO port 0.
 * @param pin_swdio pin number for SBWTDIO signal. Note: Only supports pins of GPIO port 0.
 * @param pin_swdio pin number for direction signal for TDIO. Note: Only supports pins of GPIO port 0.
 * @param f_clk frequency of SBWTCK signal
 *
 * @returns DRV_SUCCESS on success
 */
static int sbw_dev_connect(const uint8_t pin_sbw_tck, const uint8_t pin_sbw_tdio,
                           const uint8_t pin_sbw_dir, const uint32_t f_clk)
{
    // init (separate part for Riotee-impl)
    sbw_transport_init(pin_sbw_tck, pin_sbw_tdio, pin_sbw_dir, f_clk);

#define OPEN_FORCED
#ifdef OPEN_FORCED
    const int rc1 = sbw_jtag_connect();  // SUCCESS | ERR_GENERIC
    const int rc2 = sbw_jtag_sync();     // SUCCESS | ERR_GENERIC
    const int rc3 = sbw_dev_reset();     // SUCCESS | ERR_GENERIC
    const int rc4 = DisableMpu_430Xv2(); // SUCCESS | ERR_GENERIC
    if (rc1 != SBW_SUCCESS) return rc1;
    if (rc2 != SBW_SUCCESS) return rc2;
    if (rc3 != SBW_SUCCESS) return rc3;
    if (rc4 != SBW_SUCCESS) return rc4;
#else

    // connect
    int rc;
    if ((rc = sbw_jtag_connect()) != SBW_SUCCESS) return rc; // SUCCESS | ERR_GENERIC
    if (is_lock_key_programmed()) return SBW_ERR_GENERIC;    // true | false
    uint16_t core_id;
    if ((rc = sbw_dev_get_coreip_id(&core_id)) != SBW_SUCCESS) return rc; // SUCCESS | ERR_GENERIC
    if ((rc = sbw_jtag_sync()) != SBW_SUCCESS) return rc;                 // SUCCESS | ERR_GENERIC
    if ((rc = sbw_dev_reset()) != SBW_SUCCESS) return rc;                 // SUCCESS | ERR_GENERIC

    // TODO: riotee does not have this specialization below
    // Disables FRAM write protection
    if ((rc = DisableMpu_430Xv2()) != SBW_SUCCESS) // SUCCESS | ERR_GENERIC
    {
        sbw_dev_disconnect();
        return rc;
    }
#endif
    return DRV_SUCCESS;
}


/**
 * Writes a word to the target memory
 *
 * @param target memory address
 * @param data word to be written
 *
 * TODO: replace by new version
 */
static int write(uint32_t data, uint32_t address)
{
#if DISABLE_JTAG_SIGNATURE_WRITE
    /* Prevent write to JTAG signature region -> this would disable JTAG access */
    if ((address >= JTAG_SIGNATURE_LOW) && (address < JTAG_SIGNATURE_HIGH))
    {
        return DRV_ERR_PROTECTED;
    }
#endif
    if (mem_write_word((uint16_t) address, (uint16_t) data) != 0) return DRV_ERR_GENERIC;
    return DRV_SUCCESS;
}

/**
 * Reads a word from the specified address in memory.
 *
 * @param dst pointer to destination
 * @param addr target memory address
 *
 * TODO: replace by new version
 */
static int read(uint32_t *const dst, uint32_t address)
{
    if (mem_read_word((uint16_t *) dst, (uint16_t) address) != SBW_SUCCESS) return DRV_ERR_GENERIC;
    return DRV_SUCCESS;
}

// TODO: make riotee-version usable -> change device-api?
int sbw_dev_mem_read(uint16_t *dst, uint32_t addr, size_t n_words)
{
    int rc;
    for (unsigned int i = 0; i < n_words; i++)
    {
        if ((rc = mem_read_word(dst + i, addr + 2 * i)) != SBW_SUCCESS) return rc;
    }
    return SBW_SUCCESS;
}

// TODO: make riotee-version usable -> change device-api?
int sbw_dev_mem_write(uint32_t addr, uint16_t *data, size_t n_words)
{
    int rc;
    for (unsigned int i = 0; i < n_words; i++)
    {
        if ((rc = mem_write_word(addr + 2 * i, data[i])) != SBW_SUCCESS) return rc;
    }
    return SBW_SUCCESS;
}

/**
 * Verifies a word at the specified address in memory.
 *
 * @param address target memory address
 * @param data expected memory content
 */
static int verify(const uint32_t data, uint32_t address)
{
    uint16_t read_back;
    if (mem_read_word(&read_back, (uint16_t) address) != SBW_SUCCESS) return DRV_ERR_VERIFY;

    if ((data & 0xFFFF) == read_back) return DRV_SUCCESS;
    else return DRV_ERR_VERIFY;
}

/* Emulates a flash erase by sequentially setting memory to 1s */
#define ACTIVATE_ERASE
#ifdef ACTIVATE_ERASE
static int sbw_dev_erase()
{
    // No real erase on FRAM available -> emulate FLASH erase
    for (uint32_t address = FRAM_LOW; address < FRAM_HIGH; address += 2u)
    {
        const int ret = write(0xFFFFu, address);

        if ((ret != DRV_SUCCESS) && (ret != DRV_ERR_PROTECTED)) return DRV_ERR_GENERIC;
    }
    return DRV_SUCCESS;
}
#elif
/* FRAM doesn't need erase before write -> just ignore function call */
static int sbw_dev_erase() { return DRV_SUCCESS; }
#endif

device_driver_t msp430fr_driver = {
        .open             = sbw_dev_connect,
        .erase            = sbw_dev_erase,
        .write            = write,
        .read             = read,
        .verify           = verify,
        .close            = sbw_dev_disconnect,
        .word_width_bytes = 2u,
};
