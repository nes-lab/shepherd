# Comparison of PRU-compilations

## 2026

- GCC 15.1 action https://github.com/nes-lab/shepherd/actions/runs/26105454588/job/76767871518
- GCC 16.1 action https://github.com/nes-lab/shepherd/actions/runs/26105845700/job/76769290223
- CGT v2.3.3

```
Gnupru 2025.05 - GCC 15.1
	text	   data	    bss	    dec	    hex	filename
   7484	    496	    544	   8524	   214c	gen_gcc/pru0-shepherd-EMU-fw.elf
   4736	      0	    616	   5352	   14e8	gen_gcc/pru0-shepherd-HRV-fw.elf
   2396	      0	    552	   2948	    b84	gen_gcc/pru1-shepherd-fw.elf
   4164	    342	    544	   5050	   13ba	gen_gcc/pru0-programmer-SWD-fw.elf
   5448	    345	    544	   6337	   18c1	gen_gcc/pru0-programmer-SBW-fw.elf
Gnupru 2026.05 - GCC 16.1
   7540	    496	    544	   8580	   2184	gen_gcc/pru0-shepherd-EMU-fw.elf
   4648	      0	    616	   5264	   1490	gen_gcc/pru0-shepherd-HRV-fw.elf
   2352	      0	    552	   2904	    b58	gen_gcc/pru1-shepherd-fw.elf
   4156	    342	    544	   5042	   13b2	gen_gcc/pru0-programmer-SWD-fw.elf
   5396	    345	    544	   6285	   188d	gen_gcc/pru0-programmer-SBW-fw.elf
CGT v2.3.3
   7784     300     524    8608    21a0 gen/pru0-shepherd-EMU.out
   5056     200     536    5792    16a0 gen/pru0-shepherd-HRV.out
   2004      58     512    2574     a0e gen/pru1-shepherd.out
   5768     102     804    6674    1a12 gen/pru0-programmer-SWD.out
   7944     112     796    8852    2294 gen/pru0-programmer-SBW.out
```


## 2025

- GCC 15.1 action: https://github.com/nes-lab/shepherd/actions/runs/15343379026/job/43174242856
- GCC 14.1 action: https://github.com/nes-lab/shepherd/actions/runs/15308861373/job/43068333598
- GCC 13.1 action: https://github.com/nes-lab/shepherd/actions/runs/15343636460/job/43175016523
- CGT v2.3.3

```
elf/byte   text	   data	    bss	    dec	    hex	filename

88164    8112	    420	    544	   9076	   2374	pru0-shepherd-EMU-fw gcc-13.1
90048    8140	    420	    544	   9104	   2390	pru0-shepherd-EMU-fw gcc-14.1
85152    7744	    420	    544	   8708	   2204	pru0-shepherd-EMU-fw gcc-15.1
84152    7600       332     544    8476    211c pru0-shepherd-EMU-fw cgt-2.3.3

70496    5172	      0	    596	   5768	   1688	pru0-shepherd-HRV-fw.elf gcc-13.1
70428    5172	      0	    596	   5768	   1688	pru0-shepherd-HRV-fw.elf gcc-14.1
69324    4808	      0	    596	   5404	   151c	pru0-shepherd-HRV-fw.elf gcc-15.1
76300    5168       220     544    5932    172c pru0-shepherd-HRV-fw.elf cgt-2.3.3

34976    840	      0	    548	   1388	    56c	pru1-shepherd-fw gcc-13.1
34956	 840	      0	    548	   1388	    56c pru1-shepherd-fw gcc-14.1
42760    2364	      0	    552	   2916	    b64	pru1-shepherd-fw gcc-15.1
62804    1944        58     512    2514     9d2 pru1-shepherd-fw cgt-2.3.3

66336    4308	    342	    544	   5194	   144a	pru0-programmer-SWD-fw gcc-13.1
66188    4256	    342	    544	   5142	   1416	pru0-programmer-SWD-fw gcc-14.1
65768    4164	    342	    544	   5050	   13ba	pru0-programmer-SWD-fw gcc-15.1
79084    5756       102     804    6662    1a06 pru0-programmer-SWD-fw cgt-2.3.3

73456    5628	    345	    544	   6517	   1975	pru0-programmer-SBW-fw gcc-13.1
73380    5552	    345	    544	   6441	   1929	pru0-programmer-SBW-fw gcc-14.1
72504    5448	    345	    544	   6337	   18c1	pru0-programmer-SBW-fw gcc-15.1
83356    7932     	112     796    8840    2288 pru0-programmer-SBW-fw cgt-2.3.3
```
