#ifndef PRU0_FW_CONFIG_H_
#define PRU0_FW_CONFIG_H_

/* split of fw due to PRU-limitations
   -> select a primary mode when none is chosen
*/
#if !(defined(EMU_SUPPORT) || defined(HRV_SUPPORT))
  #define EMU_SUPPORT
#endif

#endif // PRU0_FW_CONFIG_H_
