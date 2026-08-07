#ifndef PRU_FIRMWARE_PRU1_SHEPHERD_FW_INCLUDE_INTC_MAP_H
#define PRU_FIRMWARE_PRU1_SHEPHERD_FW_INCLUDE_INTC_MAP_H

#include "commons.h"
#include <rsc_types.h>
#include <stddef.h>

/* EMPTY MAP */

#if !defined(__GNUC__)
  #pragma DATA_SECTION(my_irq_rsc, ".pru_irq_map")
  #pragma RETAIN(my_irq_rsc)
  #define __pru_irq_map /* */
#else
  #define __pru_irq_map                                                                            \
      __attribute__((section(".pru_irq_map"),                                                      \
                     unavailable("pru_irq_map is for usage by the host only")))
#endif

struct pru_irq_rsc my_irq_rsc = {
        0, /* type = 0 */
        0, /* number of system events being mapped */
        {},
};

#endif // PRU_FIRMWARE_PRU1_SHEPHERD_FW_INCLUDE_INTC_MAP_H
