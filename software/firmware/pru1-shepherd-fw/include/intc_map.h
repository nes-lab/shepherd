#ifndef PRU_FIRMWARE_PRU1_SHEPHERD_FW_INCLUDE_INTC_MAP_H
#define PRU_FIRMWARE_PRU1_SHEPHERD_FW_INCLUDE_INTC_MAP_H

/*
 * ======== PRU INTC Map ========
 *
 * Define the INTC mapping for interrupts going to the ICSS / ICSSG:
 * 	ICSS Host interrupts 0, 1
 * 	ICSSG Host interrupts 0, 1, 10-19
 *
 * Note that INTC interrupts going to the ARM Linux host should not be defined
 * in this file (ICSS/ICSSG Host interrupts 2-9).
 *
 * The INTC configuration for interrupts going to the ARM host should be defined
 * in the device tree node of the client driver, "interrupts" property.
 * See Documentation/devicetree/bindings/interrupt-controller/ti,pruss-intc.yaml
 * entry #interrupt-cells for more.
 *
 * For example, on ICSSG:
 *
 * &client_driver0 {
 * 	interrupt-parent = <&icssg0_intc>;
 * 	interrupts = <21 2 2>, <22 3 3>;
 * 	interrupt-names = "interrupt_name1", "interrupt_name2";
 * };
 *
 */

#include <stddef.h>
#include <rsc_types.h>
#include "commons.h"

/*
 * Needed for PSSP 6.0.0. / Kernel 5.10, steps
 * - remove intc in resource_table.h
 * - activate pru_irq_map-Line in .cmd-File
 * - include this file in main.c
 */


/*
 * .pru_irq_map is used by the RemoteProc driver during initialization. However,
 * the map is NOT used by the PRU firmware. That means DATA_SECTION and RETAIN
 * are required to prevent the PRU compiler from optimizing out .pru_irq_map.
 */
#pragma DATA_SECTION(my_irq_rsc, ".pru_irq_map")
#pragma RETAIN(my_irq_rsc)

struct pru_irq_rsc my_irq_rsc  = {
	0,			/* type = 0 */
	1,			/* number of system events being mapped */
	{
		{HOST_PRU_EVT_TIMESTAMP, 0, 0},	/* {sysevt, channel, host interrupt} */
	},
};


#endif //PRU_FIRMWARE_PRU1_SHEPHERD_FW_INCLUDE_INTC_MAP_H
