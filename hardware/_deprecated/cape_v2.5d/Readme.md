
## Main Goals

- replace old target connector by new edge connector
- redo interface to target completely
- add 17 V regulator to clean up POE-Supply
- add more GPIO (remove harvester as a tradeoff)

## Changes

### Implemented Changes v2.5d (compared to 2.5c)

- BOM-Trouble
  - NLAS4684 / NLAS4684FCT1G not available at all
    - Analog Switch, Dual SPDT, 500 mOhm Rds, 300 mA continuous, 500 mA peak, <10 nA Leakage (1 nA for -55 to 25°C)
    - we still have **~200x NLAS4684MN**, so will switch to that for now (+ larger, safer package)
  - PI5A4158 / PI5A4158ZAEX currently not avail
    - Analog Switch, Dual SPDT, 800 mOhm Rds, ~40 nA Leakage, high speed ~150 MHz with < 40 pF
    - PI3USB102G: 4 Ohm, 5V5 max, 6 pF, **BUT** 200 nA leakage
    - PI5A23157: 10 Ohm, 6V max, 18 pF, **BUT** 50 - 1000 nA leakage
    - **PI5A4157 / 729-PI5A4157CEX: single channel version of same IC, but only larger SC70 package (2.2x2.4) available**
    - **729-PI5A4157ZUEX**: UDFN-Package, 1x1 mm, mouser totally hides out of life parts, is in stock
  - LP2989-3.3 not avail as VSSOP-8 / TSOP
    - switch to WSON?
    - **926-LP2989AIMM33NOPB**, same but double the price
  - 10k 0402 667-ERJ-2GEJ103X -> 603-RC0402FR-7W10KL
  - 5.1k 0402 667-ERJ-2RKF5101X -> 603-RC0402FR-075K1L

## Errata & future Improvements

- 1uF 10V is both used in 0402 & 0603
- holes on panel can be 3.2 mm for stencil printer
- QR Code can now be directly created in Altium
- larger tag-field (upper left corner)
- perforated breaking lines on panels  (extension of milled line)
- cage with paste?
- JST-Connector needs paste on mech-pad
- panel-bridge under JST - bad coincidence
- screw-hole could have vias around (safer, if inner metal scrapes off) -> it already has
- show label on 10mV
- add testpoints for voltages, avoid touching components
- Label reads "v2.5c" not 2.5d
- pin 1 marking bigger on most ICs
- **uart-sys pins are swapped, R66 & R68 need to be crossed manually**

Up to here implemented in v2.5e

- header to interface SBC as SMD?
- NOTE: PI5 is the hardest part to place & source (but has to be replaced anyway)
