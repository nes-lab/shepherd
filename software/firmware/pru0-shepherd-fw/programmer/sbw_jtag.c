#include <stdint.h>

#include "sys_gpio.h"
#include "delay.h"
#include "programmer/sbw_jtag.h"
#include "programmer/sbw_transport.h"

//*****************************************************************************
//
// Reset SBW TAP controller
//
//*****************************************************************************
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

//*****************************************************************************
//
//! \brief This function checks if the JTAG lock key is programmed.
//! \return word (STATUS_OK if fuse is blown, STATUS_ERROR otherwise)
//
//*****************************************************************************
int IsLockKeyProgrammed(void)
{
	uint16_t i;

	for (i = 3; i > 0; i--) //  First trial could be wrong
	{
		IR_Shift(IR_CNTRL_SIG_CAPTURE);
		if (DR_Shift16(0xAAAA) == 0x5555) {
			return (SC_ERR_GENERIC); // Fuse is blown
		}
	}
	return (SC_ERR_NONE); // Fuse is not blown
}

//*****************************************************************************
//
// Shift bits
//
//*****************************************************************************
uint32_t AllShifts(uint16_t Format, uint32_t Data)
{
	uint32_t TDOword = 0x00000000;
	uint32_t MSB = 0x00000000;
	uint32_t i;

	gpio_state_t tdo;

	switch (Format) {
	case F_BYTE:
		MSB = 0x00000080;
		break;
	case F_WORD:
		MSB = 0x00008000;
		break;
	case F_ADDR:
		MSB = 0x00080000;
		break;
	case F_LONG:
		MSB = 0x80000000;
		break;
	default: // this is an unsupported format, function will just return 0
		return TDOword;
	}
	// shift in bits
	for (i = Format; i > 0; i--) {
		if (i == 1) // last bit requires TMS=1; TDO one bit before TDI
		{
			tdo = ((Data & MSB) == 0) ? tmsh_tdil_tdo_rd() : tmsh_tdih_tdo_rd();

		} else {
			tdo = ((Data & MSB) == 0) ? tmsl_tdil_tdo_rd() : tmsl_tdih_tdo_rd();
		}
		Data <<= 1;
		if (tdo)
			TDOword++;
		if (i > 1)
			TDOword <<= 1; // TDO could be any port pin
	}
	tmsh_tdih(); // update IR
	if (get_tclk()) {
		tmsl_tdih();
	} else {
		tmsl_tdil();
	}

	// de-scramble bits on a 20bit shift
	if (Format == F_ADDR) {
		TDOword = ((TDOword << 16) + (TDOword >> 4)) & 0x000FFFFF;
	}

	return (TDOword);
}

//*****************************************************************************
//
// IR scan
//
//*****************************************************************************
uint32_t IR_Shift(uint8_t instruction)
{
	// JTAG FSM state = Run-Test/Idle
	if (get_tclk()) {
		tmsh_tdih();
	} else {
		tmsh_tdil();
	}
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

//*****************************************************************************
//
// 16 bit DR scan
//
//*****************************************************************************
uint16_t DR_Shift16(uint16_t data)
{
	// JTAG FSM state = Run-Test/Idle
	if (get_tclk()) {
		tmsh_tdih();
	} else {
		tmsh_tdil();
	}
	// JTAG FSM state = Select DR-Scan
	tmsl_tdih();
	// JTAG FSM state = Capture-DR
	tmsl_tdih();

	// JTAG FSM state = Shift-DR, Shift in TDI (16-bit)
	return (AllShifts(F_WORD, data));
	// JTAG FSM state = Run-Test/Idle
}

//*****************************************************************************
//
// 20 bit DR scan
//
//*****************************************************************************
uint32_t DR_Shift20(uint32_t address)
{
	// JTAG FSM state = Run-Test/Idle
	if (get_tclk()) {
		tmsh_tdih();
	} else {
		tmsh_tdil();
	}
	// JTAG FSM state = Select DR-Scan
	tmsl_tdih();
	// JTAG FSM state = Capture-DR
	tmsl_tdih();

	// JTAG FSM state = Shift-DR, Shift in TDI (16-bit)
	return (AllShifts(F_ADDR, address));
	// JTAG FSM state = Run-Test/Idle
}

//*****************************************************************************
//
//! \brief Read a 32bit value from the JTAG mailbox.
//! \return uint32_t (32bit value from JTAG mailbox)
//
//*****************************************************************************
int i_ReadJmbOut(void)
{
	uint16_t sJMBINCTL;
	uint32_t lJMBOUT = 0;
	uint16_t sJMBOUT0, sJMBOUT1;

	sJMBINCTL = 0;

	IR_Shift(IR_JMB_EXCHANGE); // start exchange
	lJMBOUT = DR_Shift16(sJMBINCTL);

	if (lJMBOUT & OUT1RDY) // check if new data available
	{
		sJMBINCTL |= JMB32B + OUTREQ;
		lJMBOUT = DR_Shift16(sJMBINCTL);
		sJMBOUT0 = (uint16_t)DR_Shift16(0);
		sJMBOUT1 = (uint16_t)DR_Shift16(0);
		lJMBOUT = ((uint32_t)sJMBOUT1 << 16) + sJMBOUT0;
	}
	return lJMBOUT;
}

//*****************************************************************************
//
//! \brief Write a 16bit value into the JTAG mailbox system.
//! The function timeouts if the mailbox is not empty after a certain number
//! of retries.
//! \param[in] uint16_t dataX (data to be shifted into mailbox)
//
//*****************************************************************************
int i_WriteJmbIn16(uint16_t dataX)
{
	uint16_t sJMBINCTL;
	uint16_t sJMBIN0;
	uint32_t Timeout = 0;
	sJMBIN0 = (uint16_t)(dataX & 0x0000FFFF);
	sJMBINCTL = INREQ;

	IR_Shift(IR_JMB_EXCHANGE);
	do {
		Timeout++;
		if (Timeout >= 3000) {
			return SC_ERR_GENERIC;
		}
	} while (!(DR_Shift16(0x0000) & IN0RDY) && Timeout < 3000);
	if (Timeout < 3000) {
		DR_Shift16(sJMBINCTL);
		DR_Shift16(sJMBIN0);
	}
	return SC_ERR_NONE;
}

//*****************************************************************************
//
//! \brief Write a 32bit value into the JTAG mailbox system.
//! The function timeouts if the mailbox is not empty after a certain number
//! of retries.
//! \param[in] uint16_t dataX (data to be shifted into mailbox)
//! \param[in] uint16_t dataY (data to be shifted into mailbox)
//
//*****************************************************************************
int i_WriteJmbIn32(uint16_t dataX, uint16_t dataY)
{
	uint16_t sJMBINCTL;
	uint16_t sJMBIN0, sJMBIN1;
	uint32_t Timeout = 0;

	sJMBIN0 = (uint16_t)(dataX & 0x0000FFFF);
	sJMBIN1 = (uint16_t)(dataY & 0x0000FFFF);
	sJMBINCTL = JMB32B | INREQ;

	IR_Shift(IR_JMB_EXCHANGE);
	do {
		Timeout++;
		if (Timeout >= 3000) {
			return SC_ERR_GENERIC;
		}
	} while (!(DR_Shift16(0x0000) & IN0RDY) && Timeout < 3000);

	if (Timeout < 3000) {
		sJMBINCTL = 0x11;
		DR_Shift16(sJMBINCTL);
		DR_Shift16(sJMBIN0);
		DR_Shift16(sJMBIN1);
	}
	return SC_ERR_NONE;
}

//*****************************************************************************
//
//! \brief Function to start the JTAG communication - RST line high - device
//! starts code execution
//
//*****************************************************************************
void EntrySequences_RstHigh_SBW()
{
	set_sbwtck(GPIO_STATE_LOW);
	delay_us(800); // delay min 800us - clr SBW controller
	set_sbwtck(GPIO_STATE_HIGH);
	delay_us(50);

	// SpyBiWire entry sequence
	// Reset Test logic
	set_sbwtdio(GPIO_STATE_LOW); // put device in normal operation: Reset = 0
	set_sbwtck(GPIO_STATE_LOW); // TEST pin = 0
	delay_ms(1); // wait 1ms (minimum: 100us)

	// SpyBiWire entry sequence
	set_sbwtdio(GPIO_STATE_HIGH); // Reset = 1
	delay_us(5);
	set_sbwtck(GPIO_STATE_HIGH); // TEST pin = 1
	delay_us(5);
	// initial 1 PIN_SBWTCKs to enter sbw-mode
	set_sbwtck(GPIO_STATE_LOW);
	delay_us(5);
	set_sbwtck(GPIO_STATE_HIGH);
}

//*****************************************************************************
//
//! \brief Function to start the SBW communication - RST line low - device do
//! not start code execution
//
//*****************************************************************************
void EntrySequences_RstLow_SBW()
{
	set_sbwtck(GPIO_STATE_LOW);
	set_sbwtdio(GPIO_STATE_LOW); // Added for Low RST
	delay_us(800); // delay min 800us - clr SBW controller
	set_sbwtck(GPIO_STATE_HIGH);
	delay_us(50);

	// SpyBiWire entry sequence
	// Reset Test logic
	set_sbwtdio(GPIO_STATE_LOW); // put device in normal operation: Reset = 0
	set_sbwtck(GPIO_STATE_LOW); // TEST pin = 0
	delay_ms(1); // wait 1ms (minimum: 100us)

	// SpyBiWire entry sequence
	set_sbwtdio(GPIO_STATE_HIGH); // Reset = 1
	delay_us(5);
	set_sbwtck(GPIO_STATE_HIGH); // TEST pin = 1
	delay_us(5);
	// initial 1 PIN_SBWTCKs to enter sbw-mode
	set_sbwtck(GPIO_STATE_LOW);
	delay_us(5);
	set_sbwtck(GPIO_STATE_HIGH);
}

//*****************************************************************************
//
//! \brief Function to enable JTAG communication with a target. Use JSBW mode
//!  if device is in LPM5 mode.
//! \return word (JTAG_ID91(0x91) if connection was established successfully,
//! invalid JTAG ID (0x1) otherwise)
//
//*****************************************************************************
uint16_t magicPattern(void)
{
	uint16_t deviceJtagID = 0;

	// Enable the JTAG interface to the device.
	ConnectJTAG();
	// Apply again 4wire/SBW entry Sequence.
	// set ResetPin = 0
	EntrySequences_RstLow_SBW();
	// reset TAP state machine -> Run-Test/Idle
	ResetTAP();
	// feed JTAG mailbox with magic pattern
	if (i_WriteJmbIn16(STOP_DEVICE) == SC_ERR_NONE) {
		// Apply again 4wire/SBW entry Sequence.

		EntrySequences_RstHigh_SBW();

		ResetTAP(); // reset TAP state machine -> Run-Test/Idle

		deviceJtagID = (uint16_t)IR_Shift(IR_CNTRL_SIG_CAPTURE);

		if (deviceJtagID == JTAG_ID91) {
			// if Device is in LPM.x5 -> reset IO lock of JTAG pins and Configure it
			// for debug
			IR_Shift(IR_TEST_3V_REG);
			DR_Shift16(0x4020);
		} else if (deviceJtagID == JTAG_ID99) {
			IR_Shift(IR_TEST_3V_REG);
			DR_Shift16(0x40A0);
		}
		return deviceJtagID;
	}
	return 1; // return 1 as an invalid JTAG ID
}

//*****************************************************************************
//
// Connect the JTAG/SBW Signals and execute delay
//
//*****************************************************************************
void ConnectJTAG()
{
	sbw_transport_connect();
	delay_ms(15);
}

//*****************************************************************************
//
// Stop JTAG/SBW by disabling the pins and executing delay
//
//*****************************************************************************
void StopJtag(void)
{
	sbw_transport_disconnect();
	delay_ms(15);
}
