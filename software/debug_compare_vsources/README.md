# Benchmarks

Systems that are compared here:

- `py`: virtual harvester implementation in shepherd-core-lib
- `cpy`: pru-code interfaced by python via ctypes (/software/firmware/pru0-python-module)
- `pru`: real pru harvesting directly from transducer on a harvesting node

The first two systems harvest from a `ivsurface` (curves), which is a compromise to allow later harvesting.

**NOTES**: `harvest_pru.py` should be run first to get the input files for the other experiments.
See setup-section below.

## Harvesting

Algorithms used

- `ivcurve`: IV-Curve with 909 steps (110 Hz)
- `cv10`: Constant Voltage = 1 V
- `cv20`: 2 V
- `mppt_voc`: generic V_OC-Regulator
- `mppt_bq_solar`: harvesting-unit of BQ-ICs set to solar
- `mppt_bq_thermoelectric`: same for wrong transducer
- `mppt_po`: perturb & observe algorithm
- `mppt_opt`: very fast po-algo

### Setup

- solar cell: IXYS SM101K09L
- lighting by philips LED 5.9 W 806 lm 2000-2700 K, 50 Hz
- lamp was ~ 10 cm above solar cell & the setup was covered with a white lampshade
- 30 s recording

### Results (complete run)

Analyze of the processed energy and error in comparison to the Py-implementation as reference.

| Harvesting             | PyRef/mWs | CPy/mWs | error/% | Pru/mWs |    error/% |
|:-----------------------|----------:|--------:|--------:|--------:|-----------:|
| ivcurve (base)         |           |         |         |  26,846 |            |
| cv10                   |    24,062 |  24,062 |   0,000 |  24,042 |      0,084 |
| cv20                   |    45,293 |  45,293 |   0,000 |  45,086 |      0,457 |
| mppt_voc               |    55,781 |  55,781 |   0,000 |  55,582 |      0,358 |
| mppt_bq_solar          |    55,587 |  55,587 |   0,000 |  55,279 |      0,554 |
| mppt_bq_thermoelectric |    42,806 |  42,806 |   0,000 |  43,281 | **-1,111** |
| mppt_po                |    56,362 |  56,362 |   0,000 |  56,172 |      0,337 |
| mppt_opt               |    57,237 |  57,237 |   0,000 |  53,415 |  **6,677** |

The main difference is visible for `PRU` running `mppt_opt` with is directly harvesting from the transducer (different approach) in comparison to the other two systems which process the `ivcurve`-recording.

### Results (2025)

|                        |   PyRef/mWs |   CPy/mWs | error/% |
|:-----------------------|------------:|----------:|--------:|
| cv10                   |     17.1429 |   17.1429 |       0 |
| cv20                   |           0 |         0 |       0 |
| mppt_voc               |     17.3837 |   17.3865 |   0.016 |
| mppt_bq_solar          |      17.249 |    17.249 |       0 |
| mppt_bq_thermoelectric |     13.9538 |   13.8756 |  0.5634 |
| mppt_po                |     15.0008 |   15.0008 |       0 |
| mppt_opt               |     17.8115 |   17.8115 |       0 |

## Emulation

Different virtual source configurations were feed with 3 different harvesting traces.
For better controllability the target is a simple resistor.

### Setup

- Target is a single 1 kOhm resistor

### Results for (legacy) Storage Cap

Analyze of the processed energy and error in comparison to the Py-implementation as reference.

| Emulation           |  PyRef/mWs |    CPy/mWs | error/% |    Pru/mWs | error/% |
|:--------------------|-----------:|-----------:|--------:|-----------:|--------:|
| ivcurve to direct   | 221,627177 | 221,827565 |   0,090 | 223,549906 |   0,860 |
| ivcurve to dio_cap  |  42,709102 |  42,697189 |   0,028 |  42,644341 |   0,152 |
| ivcurve to BQ25504  |  50,296103 |  50,295218 |   0,002 |  50,293645 |   0,005 |
| ivcurve to BQ25570  |  47,102389 |  46,996695 |   0,225 |  47,065830 |   0,078 |
| mppt_voc to direct  | 267,581691 | 267,582445 |   0,000 | 266,922316 |   0,247 |
| mppt_voc to dio_cap |  50,104021 |  50,105496 |   0,003 |  50,052582 |   0,103 |
| mppt_voc to BQ25504 |  50,289357 |  50,288394 |   0,002 |  50,286719 |   0,005 |
| mppt_voc to BQ25570 |  47,097222 |  47,044898 |   0,111 |  47,044359 |   0,112 |
| mppt_po to direct   | 237,338342 | 237,338993 |   0,000 | 236,716713 |   0,263 |
| mppt_po to dio_cap  |  50,269561 |  50,264993 |   0,009 |  50,221581 |   0,096 |
| mppt_po to BQ25504  |  50,762148 |  50,761205 |   0,002 |  50,759567 |   0,005 |
| mppt_po to BQ25570  |  47,464743 |  47,591982 |   0,267 |  47,559356 |   0,199 |

The main source of the low constant error is from the input efficiency only having a resolution of 8 bit.

### Results for Battery Model

Numbers to above results are not directly comparable as a different input was used.

|                     | PyRef/mWs | CPy/mWs | error/% | Pru/mWs | error/% |
|:--------------------|----------:|--------:|--------:|--------:|--------:|
| ivcurve to direct   |     266.8 |   266.8 |       0 | 269.222 |     0.9 |
| ivcurve to dio_cap  |     0.519 |   0.515 |   0.658 |   0.515 |   0.693 |
| ivcurve to BQ25504  |    15.738 |  15.736 |   0.009 |  15.726 |   0.073 |
| ivcurve to BQ25570  |    14.267 |  14.251 |   0.109 |  14.248 |   0.132 |
| mppt_voc to direct  |    44.533 |  44.534 |   0.002 |  44.402 |   0.297 |
| mppt_voc to dio_cap |     0.519 |   0.515 |   0.658 |   0.515 |    0.69 |
| mppt_voc to BQ25504 |    15.849 |  15.849 |   0.005 |   15.84 |   0.057 |
| mppt_voc to BQ25570 |    14.564 |  14.561 |    0.02 |  14.558 |   0.042 |
| mppt_po to direct   |    42.892 |  42.892 |   0.001 |  42.766 |   0.296 |
| mppt_po to dio_cap  |     0.519 |   0.515 |   0.658 |   0.515 |   0.693 |
| mppt_po to BQ25504  |    13.579 |  13.578 |   0.008 |  13.566 |   0.098 |
| mppt_po to BQ25570  |    12.257 |  12.254 |   0.022 |   12.22 |   0.301 |

Note that on first look the error seems increased in comparison to the results above.
But note that:

- the three `dio_cap` entries have an overall lower energy, so small deviation have bigger influence
- the three `direct` entries are probably be influenced by the discrete voltage steps (look up table)
  - an interpolation would help, but is currently out of scope for the PRU
- the emulation on PRU uses a real 1k resistor, which measured as 1003 Ohm (0.3 % off)
