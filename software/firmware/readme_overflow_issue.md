### Overflow of program memory - the Story so far

- pru1-code compiles, but pru0 fails with ~ 3 kB overflow of program memory (8 kB)
- disabling debug-symbols (`-g0`) does not change program memory, but size of elf-file gets reduced significantly
	- pru1 fw size shrinks from > 40 kB to < 8 kB
- link-time-optimization helps somewhat (`-flto`, `-fuse-linker-plugin`)
	- pru1 fw size shrinks from 7.38 kB to 6.30 kB
	- pru0 overflow reduces from 3060 byte to 2690 byte
- disabling some debug code had just minimal change (-20 byte)
- did read through gnupru github-issues, but found no clue
- did read through large parts of gcc v12.1 doc (gcc.pdf) with no luck
- enabling `-ffast-math` does nothing to our code-size (should only help with float-ops)

[more details](./readme_overflow_issue.md)


### Overflow - help from dinuxbg

Raising [this issue](https://github.com/dinuxbg/gnupru/issues/43) helped a lot.

- compiling code with `uint32`-only (replaced `uint64`) works!
- compiling u32 with `-fno-inline` overflows by 300 byte -> clean out minor FNs to allow compiling
- analyzing codes-size with u32-version, `-fno-inline`, minor cleanout:

```shell
pru-nm --size-sort --print-size out/pru-core0.elf  | grep -w '[Tt]'
[small objects omitted]
20000138 0000001c t add32
20000138 0000001c t add64
20000538 00000034 t div_uV_n4
20000154 0000004c t cal_conv_adc_raw_to_uV
200004ec 0000004c t cal_conv_uV_to_dac_raw
2000056c 00000054 t ads8691_init
20000354 00000054 t send_message.constprop.0.isra.0
200002e0 00000074 t send_status.constprop.0
20000474 00000078 t mul64
200001a0 00000080 t harvester_initialize
20000220 000000c0 t harvest_iv_cv
200003a8 000000cc t dac8562_init
200005c0 00001778 T main
```

- same with `-fno-inline`

```
[small objects omitted]
200019d8 000000a0 t converter_calc_out_power
20000590 000000c0 t harvest_iv_cv
20000338 000000c4 t converter_initialize
200003fc 000000dc t converter_update_cap_storage
200018a8 000000ec t converter_calc_inp_power
20000888 00000100 t harvest_iv_mppt_opt
20000650 00000108 t harvest_iv_mppt_voc
20001000 0000010c t handle_kernel_com.constprop.0.isra.0
200012dc 00000120 t harvest_adc_mppt_voc
20000758 00000130 t harvest_iv_mppt_po
200011a0 0000013c t harvest_adc_ivcurve
20000a10 00000148 t converter_update_states_and_output.constprop.0
20001a78 00000148 t sample_emulator.constprop.0
20000e24 00000158 t handle_buffer_swap.constprop.0
20001e1c 000001c0 T main
200013fc 000001c4 t harvest_adc_mppt_po
20001678 000001cc t sample_init.constprop.0
20001c04 00000218 t event_loop.constprop.0
```

- gnuprumcu size-hack

```
cd tools/pru-elf-2022.05.amd64/pru-elf/lib/device-specs
sudo cp am335x.pru0 am335xl.pru0
sudo nano am335xl.pru0
	-> change imem from 8 to 18, save
change target in makefile
```

- analyze code-size with original u64-version, inline and size-hack for gnuprumcu

```
20002a38 00000038 T __pruabi_mpyll
200029e4 00000054 T __gnu_ashldi3
20002990 00000054 T __gnu_lshrdi3
200029e4 00000054 T __pruabi_lslll
20002990 00000054 T __pruabi_lsrll
200006bc 00000054 t ads8691_init
200003a4 00000054 t send_message.constprop.0.isra.0
20000660 0000005c t div_uV_n4
20000330 00000074 t send_status.constprop.0
200005e8 00000078 t cal_conv_uV_to_dac_raw
200001f0 00000080 t harvester_initialize
20000138 000000b8 t cal_conv_adc_raw_to_uV
20000270 000000c0 t harvest_iv_cv
200003f8 000000cc t dac8562_init
200004c4 00000124 t mul64
20000710 00002280 T main
```

- same with `-fno-inline`

```
20000198 0000000c t calibration_initialize
200003b4 0000000c t get_state_log_intermediate
2000018c 0000000c t simple_mutex_exit
20000168 00000010 t iep_get_cnt_val
20000138 00000010 t iep_get_tmr_cmp_sts
20000178 00000014 t simple_mutex_enter
2000032c 00000014 t sub32
20000888 00000018 t ring_init.constprop.0
200002b4 0000001c t add32
20000148 00000020 t iep_clear_evt_cmp
200008a0 00000020 t set_batok_pin.constprop.0
20000d3c 00000024 t get_V_intermediate_raw
20000390 00000024 t get_V_intermediate_uV
200012d4 00000030 t sample_dbg_adc
200028ac 00000038 T __pruabi_mpyll
20000fc8 0000003c t get_I_mid_out_nA
20002150 00000044 t get_output_inv_efficiency_n4
20000910 00000044 t ring_get.constprop.0
200023e4 00000044 t sample.constprop.0
20000340 00000050 t cal_conv_adc_raw_to_uV
200008c0 00000050 t ring_put.constprop.0
20000838 00000050 t sample_iv_harvester
20002858 00000054 T __gnu_ashldi3
20002804 00000054 T __gnu_lshrdi3
20002858 00000054 T __pruabi_lslll
20002804 00000054 T __pruabi_lsrll
20001d20 00000054 t ads8691_init
200013e4 00000054 t send_message.constprop.0.isra.0
20000f6c 0000005c t div_uV_n4
20001218 0000005c t sample_emu_ADCs
200002d0 0000005c t sub64
20001274 00000060 t sample_hrv_ADCs
20001f48 00000064 t get_input_efficiency_n8
200001b4 00000064 t mul32
20001cbc 00000064 t sample_adc_harvester
20001378 0000006c t receive_message.constprop.0
20001304 00000074 t send_status.constprop.0
20000b3c 00000078 t cal_conv_uV_to_dac_raw
200003c0 00000080 t harvester_initialize
200015ac 00000084 t sample_dbg_dac
20001808 00000094 t harvest_adc_cv
20000218 0000009c t add64
20000440 000000c0 t harvest_iv_cv
20000a78 000000c4 t cal_conv_adc_raw_to_nA
2000173c 000000cc t dac8562_init
20000738 00000100 t harvest_iv_mppt_opt
20002194 00000108 t converter_calc_out_power
20000500 00000108 t harvest_iv_mppt_voc
20001630 0000010c t handle_kernel_com.constprop.0.isra.0
200019d8 00000120 t harvest_adc_mppt_voc
20000954 00000124 t mul64
20000608 00000130 t harvest_iv_mppt_po
2000189c 0000013c t harvest_adc_ivcurve
2000229c 00000148 t sample_emulator.constprop.0
20001438 00000174 t handle_buffer_swap.constprop.0
20000bb4 00000188 t converter_initialize
20001fac 000001a4 t converter_calc_inp_power
20001af8 000001c4 t harvest_adc_mppt_po
20002640 000001c4 T main
20001d74 000001d4 t sample_init.constprop.0
20000d60 0000020c t converter_update_states_and_output.constprop.0
20001004 00000214 t converter_update_cap_storage
20002428 00000218 t event_loop.constprop.0
```

- compiling original code (u64) with `-fno-inline` without size-hack reduces overflow from 2672 to 2276 bytes.
	- is this a self-made inline-fuckup?
	- removing `inline` from our codebase brings overflow back to 2672 bytes
	- that is strange!

- direct compare of the biggest FNs
  - u64-heavy Fns grow by factor 1.6 to 2.4

```
u64 u32 x fn_name
108 0a0 t converter_calc_out_power              -> 264 vs 160 bytes
    0c0 t harvest_iv_cv
188 0c4 t converter_initialize                  -> 392 vs 196 bytes
214 0dc t converter_update_cap_storage          -> 532 vs 220 bytes
1a4 0ec t converter_calc_inp_power              -> 420 vs 236 bytes
100 100 t harvest_iv_mppt_opt
120 108 t harvest_iv_mppt_voc
10c 10c t handle_kernel_com
120 120 t harvest_adc_mppt_voc
130 130 t harvest_iv_mppt_po
13c 13c t harvest_adc_ivcurve
20c 148 t converter_update_states_and_output    -> 524 vs 328 bytes
148 148 t sample_emulator
174 158 t handle_buffer_swap
1c4 1c0 T main
1c4 1c4 t harvest_adc_mppt_po
1d4 1cc t sample_init
218 218 t event_loop
```


### ~~Overflow - next steps (proposal)~~ -> obsolete, see readme.md

- generate size-map of mem-regions
	- GCC: `pru-nm --size-sort --print-size out/pru-core0.elf  | grep -w '[Tt]'`
      - `pru-size gen_gcc/pru0-shepherd-fw.elf`
    - CGT: should also be compatible with pru-nm or `pru-size gen/pru-shepherd-fw.out`
	- do sizes look plausible?
	- how does the result compare to Ti compiler?
	- working pru1-compilation may provide clues - is it also increasing size?
- possible culprits
	- u64-math may produce more complex routines
	- [32 Bit registers](https://github.com/dinuxbg/gnupru/wiki/ABI) instead of 16 Bit -> `-mabi=ti` could be the solution, but fails
		- abi=ti produces undefined references to memcpy and memset -> flag [can't use c std lib](https://gcc.gnu.org/onlinedocs/gcc-12.1.0/gcc/PRU-Options.html#PRU-Options)
	- accidental included soft-float emulation? no way found to prevent this in GCC
