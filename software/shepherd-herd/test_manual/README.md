# Benchmarks

Systems that are compared here:

- `py`: virtual harvester implementation in shepherd-core-lib
- `c-py`: pru-code interfaced by python via ctypes (/software/firmware/pru0-python-module)
- `pru`: real pru harvesting directly from transducer

The first two systems harvest from `ivcurves`, which is a compromise to allow later harvesting.

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

### Results

Analyze of the processed energy and error in comparison to the Py-implementation as reference.

| Harvesting             | Py/mWs | C-Py/mWs | error/% | PRU/mWs | error/%    |
|------------------------|--------|----------|---------|---------|------------|
| ivcurve (base)         |        |          |         | 26,846  |            |
| cv10                   | 24,062 | 24,062   | 0,000   | 24,042  | 0,084      |
| cv20                   | 45,293 | 45,293   | 0,000   | 45,086  | 0,457      |
| mppt_voc               | 55,781 | 55,781   | 0,000   | 55,582  | 0,358      |
| mppt_bq_solar          | 55,587 | 55,587   | 0,000   | 55,279  | 0,554      |
| mppt_bq_thermoelectric | 42,806 | 42,806   | 0,000   | 43,281  | **-1,111** |
| mppt_po                | 56,362 | 56,362   | 0,000   | 56,172  | 0,337      |
| mppt_opt               | 57,237 | 57,237   | 0,000   | 53,415  | **6,677**  |

The main difference is visible for `PRU` running `mppt_opt` with is directly harvesting from the transducer (different approach) in comparison to the other two systems which process the `ivcurve`-recording.

## Emulation

Different virtual source configurations were feed with 3 different harvesting traces. For better controllability the target is a simple resistor.

### Setup

- Target is a single 1 kOhm resistor

### Results

Analyze of the processed energy and error in comparison to the Py-implementation as reference.

| Emulation           | Py/mWs     | C-Py/mWs   | error/% | PRU/mWs    | error/% |
|---------------------|------------|------------|---------|------------|---------|
| ivcurve to direct   | 238,514834 | 238,551795 | 0,015   | 237,957013 | 0,234   |
| ivcurve to dio_cap  | 51,181966  | 51,181283  | -0,001  | 51,180749  | 0,002   |
| ivcurve to BQ25504  | 50,293696  | 50,292813  | -0,002  | 50,291193  | 0,005   |
| ivcurve to BQ25570  | 47,10007   | 46,994343  | -0,225  | 47,06352   | 0,078   |
| mppt_voc to direct  | 267,581982 | 267,582445 | 0,000   | 266,889329 | 0,259   |
| mppt_voc to dio_cap | 50,01102   | 50,011117  | 0,000   | 50,009699  | 0,003   |
| mppt_voc to BQ25504 | 50,289405  | 50,288394  | -0,002  | 50,286746  | 0,005   |
| mppt_voc to BQ25570 | 47,097267  | 47,044898  | -0,111  | 47,044391  | 0,112   |
| mppt_po to direct   | 237,338342 | 237,338993 | 0,000   | 236,746732 | 0,249   |
| mppt_po to dio_cap  | 50,193663  | 50,193853  | 0,000   | 50,187478  | 0,012   |
| mppt_po to BQ25504  | 50,762194  | 50,761248  | -0,002  | 50,754587  | 0,015   |
| mppt_po to BQ25570  | 47,464787  | 47,591982  | 0,267   | 47,554642  | -0,189  |

The main source of the low constant error is from the input efficiency only having a resolution of 8 bit.
