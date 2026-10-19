# Benchmark Results

## 2026-10-07 - Testbed / Baseline before Optimizations

NOTE:

- Shepherd-Sheep v2026.8.1
- Shepherd-Core v2026.7.1

### One Observer to NAS

| type                           | cpu_min | cpu_max | cpu_mean | MiB/s | note                   |
|--------------------------------|---------|---------|----------|-------|------------------------|
| EMU optimized ivtrace          | 54      | 100     | 72.5     | 1.087 | had errors, incomplete |
| EMU optimized notrace          | 31      | 100     | 44.5     | 0.002 |                        |
| EMU uart datarate57600         | 63      | 100     | 82.5     | 0.685 |                        |
| EMU uart datarate57600         | 63      | 100     | 82.5     | 0.685 |                        |
| EMU input-option=native+static | 59      | 100     | 73.8     | 0.474 | had errors             |
| EMU input-option=native+random | 52      | 100     | 78.8     | 0.684 | had errors, incomplete |
| EMU input-option=scaled+static | 59      | 100     | 73.4     | 0.475 |                        |
| EMU input-option=scaled+random | 63      | 100     | 79.9     | 0.687 |                        |
| EMU t_offset=15                | 0       | 100     | 88.9     | 0.002 | had errors, incomplete |
| EMU t_offset=20                | 0       | 100     | 89.9     | 0.002 | had errors, incomplete |
| EMU t_offset=25                | 62      | 100     | 86.1     | 0.685 |                        |
| EMU t_offset=30                | 19      | 99      | 77.6     | 0.686 |                        |
| EMU power & samplerate=10      | 47      | 100     | 63.8     | 0.003 |                        |
| EMU power & samplerate=100     | 52      | 93      | 64.3     | 0.003 |                        |
| EMU power & samplerate=1000    | 57      | 100     | 69.5     | 0.010 |                        |
| EMU power & samplerate=100000  | 68      | 100     | 82.8     | 0.501 |                        |
| EMU iv & samplerate=10         | 42      | 88      | 56.7     | 0.003 |                        |
| EMU iv & samplerate=100        | 44      | 100     | 58.6     | 0.003 |                        |
| EMU iv & samplerate=1000       | 44      | 100     | 58.6     | 0.010 |                        |
| EMU iv & samplerate=100000     | 66      | 100     | 79.1     | 0.687 |                        |
| EMU output-compression=None    | 39      | 100     | 59.6     | 1.530 |                        |
| EMU output-compression=lzf     | 56      | 100     | 71.0     | 1.093 |                        |
| EMU output-compression=1       | 64      | 100     | 78.8     | 0.685 | had errors             |
| EMU input-compression=None     | 64      | 100     | 78.2     | 0.687 |                        |
| EMU input-compression=lzf      | 64      | 100     | 80.5     | 0.685 | had errors, incomplete |
| EMU input-compression=1        | 68      | 100     | 90.3     | 0.688 | high load              |

### Local SD-Card

| type                           | cpu_min | cpu_max | cpu_mean | MiB/s | note                   |
|--------------------------------|---------|---------|----------|-------|------------------------|
| EMU optimized ShpInput ivtrace | 46      | 100     | 70.3     | 1.090 | had errors             |
| EMU optimized ShpInput notrace | 30      | 99      | 47.1     | 0.002 |                        |
| EMU gpio datarate57600         | 54      | 100     | 73.5     | 0.989 |                        |
| EMU gpio datarate115200        | 59      | 100     | 78.3     | 1.168 |                        |
| EMU gpio datarate230400        | 70      | 100     | 88.8     | 1.518 |                        |
| EMU gpio datarate460800        | 39      | 100     | 98.1     | 2.099 | high load              |
| EMU gpio datarate921600        | 68      | 100     | 99.3     | 1.278 | had errors, high load  |
| EMU gpio datarate1000000       | 94      | 100     | 99.8     | 1.250 | had errors, high load  |
| EMU input-option=native+static | 53      | 100     | 67.9     | 0.788 |                        |
| EMU input-option=native+random | 58      | 100     | 71.4     | 1.088 | had errors, incomplete |
| EMU input-option=scaled+static | 51      | 100     | 67.8     | 0.786 | had errors, incomplete |
| EMU input-option=scaled+random | 57      | 99      | 72.2     | 1.092 |                        |
| EMU t_offset=15                | 0       | 99      | 85.8     | 0.002 | incomplete             |
| EMU t_offset=20                | 0       | 100     | 87.5     | 0.002 | had errors, incomplete |
| EMU t_offset=25                | 56      | 100     | 73.7     | 1.088 | had errors, incomplete |
| EMU t_offset=30                | 55      | 91      | 70.3     | 1.092 |                        |
| EMU power & samplerate=10      | 48      | 100     | 64.0     | 0.003 |                        |
| EMU power & samplerate=100     | 52      | 100     | 65.7     | 0.004 |                        |
| EMU power & samplerate=1000    | 52      | 100     | 69.2     | 0.013 |                        |
| EMU power & samplerate=100000  | 49      | 100     | 80.5     | 0.762 |                        |
| EMU iv & samplerate=10         | 44      | 100     | 58.9     | 0.003 |                        |
| EMU iv & samplerate=100        | 43      | 100     | 58.4     | 0.004 |                        |
| EMU iv & samplerate=1000       | 44      | 100     | 60.0     | 0.015 |                        |
| EMU iv & samplerate=100000     | 58      | 100     | 71.9     | 1.089 | had errors, incomplete |
| EMU output-compression=None    | 44      | 90      | 57.8     | 1.530 |                        |
| EMU output-compression=lzf     | 56      | 100     | 71.5     | 1.093 |                        |
| EMU output-compression=1       | 66      | 100     | 80.4     | 0.687 |                        |
| EMU input-compression=None     | 56      | 100     | 71.6     | 1.089 | had errors, incomplete |
| EMU input-compression=lzf      | 57      | 100     | 72.4     | 1.089 | had errors, incomplete |
| EMU input-compression=1        | 56      | 100     | 75.2     | 1.093 |                        |

## 2026-10-06 - local sd-card, dev-version, start of tuning

Learnings for us:

- input should be scaled to match gain of PRU
- input & output should be lzf (despite being not standard-conform)
- min settle time is 15 s
Learnings for the user:
- downsampling is a good idea to increase headroom for GPIO / Uart logging
- turning off power-tracing is also possible
- gpio-traffic can be continuous @ 200 kSps

| type                           | cpu_min | cpu_max | cpu_mean | MiB/s | note                  |
|--------------------------------|---------|---------|----------|-------|-----------------------|
| EMU optimized ivtrace          | 36      | 70      | 50.7     | 0.480 |                       |
| EMU optimized notrace          | 10      | 45      | 15.8     | 0.002 | (REDO after fix)      |
| EMU hrvformat-input ivtrace    | 36      | 60      | 46.9     | 0.435 |                       |
| EMU gpio datarate9600          | 37      | 100     | 52.7     | 0.171 |                       |
| EMU gpio datarate19200         | 37      | 84      | 49.7     | 0.184 |                       |
| EMU gpio datarate57600         | 37      | 86      | 53.6     | 0.237 |                       |
| EMU gpio datarate115200        | 50      | 93      | 61.0     | 0.313 |                       |
| EMU gpio datarate230400        | 63      | 96      | 73.0     | 0.438 |                       |
| EMU gpio datarate460800        | 65      | 100     | 93.5     | 0.653 | high load             |
| EMU gpio datarate921600        | 86      | 100     | 99.7     | 0.963 | high load             |
| EMU gpio datarate1000000       | 76      | 100     | 99.4     | 1.034 | high load             |
| EMU input-option=native+static | 30      | 62      | 48.2     | 0.117 |                       |
| EMU input-option=native+random | 43      | 68      | 56.0     | 0.365 |                       |
| EMU input-option=scaled+static | 35      | 62      | 46.2     | 0.117 |                       |
| EMU input-option=scaled+random | 13      | 80      | 53.6     | 0.365 |                       |
| EMU t_offset=15                | 38      | 67      | 57.2     | 0.365 |                       |
| EMU t_offset=20                | 8       | 74      | 56.4     | 0.365 |                       |
| EMU t_offset=25                | 40      | 66      | 56.8     | 0.365 |                       |
| EMU t_offset=30                | 16      | 74      | 56.1     | 0.365 |                       |
| EMU power & samplerate=10      | 11      | 76      | 45.9     | 0.002 |                       |
| EMU power & samplerate=100     | 30      | 60      | 46.5     | 0.002 |                       |
| EMU power & samplerate=1000    | 32      | 60      | 48.0     | 0.006 |                       |
| EMU power & samplerate=100000  | 67      | 100     | 98.2     | 0.143 | had errors, high load |
| EMU iv & samplerate=10         | 26      | 57      | 41.6     | 0.002 |                       |
| EMU iv & samplerate=100        | 26      | 50      | 41.5     | 0.002 |                       |
| EMU iv & samplerate=1000       | 24      | 60      | 41.5     | 0.005 |                       |
| EMU iv & samplerate=100000     | 40      | 64      | 56.3     | 0.365 |                       |
| EMU output-compression=None    | 28      | 66      | 45.6     | 1.529 |                       |
| EMU output-compression=lzf     | 20      | 67      | 54.0     | 0.434 |                       |
| EMU output-compression=1       | 21      | 70      | 56.4     | 0.365 |                       |
| EMU output-compression=6       | 16      | 76      | 64.4     | 0.351 |                       |
| EMU input-compression=None     | 24      | 68      | 55.4     | 0.365 |                       |
| EMU input-compression=lzf      | 39      | 68      | 55.3     | 0.365 |                       |
| EMU input-compression=1        | 39      | 68      | 57.6     | 0.365 |                       |
| EMU input-compression=6        | 9       | 74      | 56.2     | 0.365 |                       |
| HRV t_offset=10                | 28      | 90      | 38.2     | 0.135 | settle longer!        |
| HRV t_offset=15                | 29      | 40      | 34.4     | 0.135 |                       |
| HRV t_offset=20                | 29      | 41      | 34.3     | 0.136 |                       |
| HRV t_offset=25                | 22      | 42      | 33.9     | 0.135 |                       |
| HRV power & samplerate=10      | 24      | 44      | 28.8     | 0.002 |                       |
| HRV power & samplerate=100     | 24      | 47      | 29.4     | 0.002 |                       |
| HRV power & samplerate=1000    | 24      | 40      | 30.5     | 0.003 |                       |
| HRV power & samplerate=100000  | 19      | 100     | 98.7     | 0.036 | high load             |
| HRV iv & samplerate=10         | 21      | 48      | 25.0     | 0.002 |                       |
| HRV iv & samplerate=100        | 19      | 40      | 24.7     | 0.002 |                       |
| HRV iv & samplerate=1000       | 20      | 47      | 25.2     | 0.003 |                       |
| HRV iv & samplerate=100000     | 28      | 41      | 34.4     | 0.135 |                       |
| HRV compression=None           | 23      | 39      | 29.4     | 1.529 |                       |
| HRV compression=lzf            | 24      | 47      | 30.8     | 0.174 |                       |
| HRV compression=1              | 27      | 42      | 34.1     | 0.135 |                       |
| HRV compression=6              | 30      | 46      | 38.4     | 0.120 |                       |

## tune gpio-sampling

### baseline (from above)

| type                     | cpu_min | cpu_max | cpu_mean | MiB/s | note      |
|--------------------------|---------|---------|----------|-------|-----------|
| EMU gpio datarate57600   | 37      | 86      | 53.6     | 0.237 |           |
| EMU gpio datarate115200  | 50      | 93      | 61.0     | 0.313 |           |
| EMU gpio datarate230400  | 63      | 96      | 73.0     | 0.438 |           |
| EMU gpio datarate460800  | 65      | 100     | 93.5     | 0.653 | high load |
| EMU gpio datarate921600  | 86      | 100     | 99.7     | 0.963 | high load |
| EMU gpio datarate1000000 | 76      | 100     | 99.4     | 1.034 | high load |

### chunk=increment, lzf-out, shuffle

| type                        | cpu_min | cpu_max | cpu_mean | MiB/s | note      |
|-----------------------------|---------|---------|----------|-------|-----------|
| EMU optimized ivtrace       | 40      | 62      | 52.9     | 0.480 |           |
| EMU optimized notrace       | 14      | 53      | 23.9     | 0.002 |           |
| EMU hrvformat-input ivtrace | 39      | 60      | 52.4     | 0.480 |           |
| EMU gpio datarate57600      | 38      | 78      | 53.0     | 0.281 |           |
| EMU gpio datarate115200     | 46      | 89      | 58.8     | 0.371 |           |
| EMU gpio datarate230400     | 54      | 100     | 68.8     | 0.521 |           |
| EMU gpio datarate460800     | 67      | 100     | 85.2     | 0.771 |           |
| EMU gpio datarate921600     | 85      | 100     | 99.8     | 1.128 | high load |
| EMU gpio datarate1000000    | 58      | 100     | 99.3     | 1.228 | high load |

### gpio non-shuffle, iv with 5x increment

| type                        | cpu_min | cpu_max | cpu_mean | MiB/s | note      |
|-----------------------------|---------|---------|----------|-------|-----------|
| EMU optimized ivtrace       | 28      | 62      | 49.5     | 0.480 |           |
| EMU optimized notrace       | 12      | 53      | 23.7     | 0.002 |           |
| EMU hrvformat-input ivtrace | 37      | 60      | 49.9     | 0.480 |           |
| EMU gpio datarate57600      | 36      | 81      | 50.0     | 0.280 |           |
| EMU gpio datarate115200     | 43      | 94      | 56.8     | 0.369 |           |
| EMU gpio datarate230400     | 52      | 92      | 66.5     | 0.522 |           |
| EMU gpio datarate460800     | 72      | 100     | 83.6     | 0.774 |           |
| EMU gpio datarate921600     | 89      | 100     | 99.8     | 1.127 | high load |
| EMU gpio datarate1000000    | 11      | 100     | 98.4     | 1.227 | high load |

### h5-optimizations, reshape 10x chunk-size

| type                     | cpu_min | cpu_max | cpu_mean | MiB/s | note      |
|--------------------------|---------|---------|----------|-------|-----------|
| EMU gpio datarate57600   | 32      | 87      | 49.4     | 0.290 |           |
| EMU gpio datarate115200  | 39      | 86      | 54.5     | 0.373 |           |
| EMU gpio datarate230400  | 48      | 90      | 63.9     | 0.520 |           |
| EMU gpio datarate460800  | 65      | 98      | 77.4     | 0.768 |           |
| EMU gpio datarate921600  | 90      | 100     | 99.8     | 1.138 | high load |
| EMU gpio datarate1000000 | 89      | 100     | 99.8     | 1.222 | high load |

### preshape & gpio reshape 100x chunk-size

| type                        | cpu_min | cpu_max | cpu_mean | MiB/s | note      |
|-----------------------------|---------|---------|----------|-------|-----------|
| EMU optimized ivtrace       | 14      | 58      | 47.8     | 0.478 |           |
| EMU optimized notrace       | 8       | 49      | 22.9     | 0.001 |           |
| EMU hrvformat-input ivtrace | 39      | 55      | 48.6     | 0.478 |           |
| EMU gpio datarate57600      | 34      | 77      | 48.3     | 0.287 |           |
| EMU gpio datarate115200     | 42      | 86      | 53.3     | 0.372 |           |
| EMU gpio datarate230400     | 51      | 92      | 62.3     | 0.519 |           |
| EMU gpio datarate460800     | 66      | 97      | 76.1     | 0.768 |           |
| EMU gpio datarate921600     | 86      | 100     | 96.9     | 1.128 | high load |
| EMU gpio datarate1000000    | 62      | 100     | 99.3     | 1.223 | high load |

## tune resampling performance

### baseline (from above)

| type                          | cpu_min | cpu_max | cpu_mean | MiB/s | note                  |
|-------------------------------|---------|---------|----------|-------|-----------------------|
| EMU power & samplerate=10     | 11      | 76      | 45.9     | 0.002 |                       |
| EMU power & samplerate=100    | 30      | 60      | 46.5     | 0.002 |                       |
| EMU power & samplerate=1000   | 32      | 60      | 48.0     | 0.006 |                       |
| EMU power & samplerate=100000 | 67      | 100     | 98.2     | 0.143 | had errors, high load |
| EMU iv & samplerate=10        | 26      | 57      | 41.6     | 0.002 |                       |
| EMU iv & samplerate=100       | 26      | 50      | 41.5     | 0.002 |                       |
| EMU iv & samplerate=1000      | 24      | 60      | 41.5     | 0.005 |                       |
| EMU iv & samplerate=100000    | 40      | 64      | 56.3     | 0.365 |                       |

### bugfixes

| type                          | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|-------------------------------|---------|---------|----------|-------|------|
| EMU power & samplerate=10     | 26      | 76      | 48.2     | 0.001 |      |
| EMU power & samplerate=100    | 13      | 70      | 48.1     | 0.002 |      |
| EMU power & samplerate=1000   | 18      | 71      | 51.5     | 0.006 |      |
| EMU power & samplerate=100000 | 39      | 66      | 53.0     | 0.360 |      |
| EMU iv & samplerate=10        | 16      | 76      | 39.2     | 0.001 |      |
| EMU iv & samplerate=100       | 24      | 66      | 39.5     | 0.002 |      |
| EMU iv & samplerate=1000      | 25      | 57      | 39.0     | 0.006 |      |
| EMU iv & samplerate=100000    | 38      | 61      | 52.6     | 0.478 |      |

### stabilize codebase

| type                          | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|-------------------------------|---------|---------|----------|-------|------|
| EMU power & samplerate=10     | 31      | 78      | 47.7     | 0.001 |      |
| EMU power & samplerate=100    | 14      | 72      | 48.4     | 0.002 |      |
| EMU power & samplerate=1000   | 12      | 73      | 51.2     | 0.005 |      |
| EMU power & samplerate=100000 | 36      | 62      | 52.5     | 0.360 |      |
| EMU iv & samplerate=10        | 16      | 70      | 39.2     | 0.001 |      |
| EMU iv & samplerate=100       | 25      | 56      | 39.3     | 0.002 |      |
| EMU iv & samplerate=1000      | 25      | 66      | 39.6     | 0.006 |      |
| EMU iv & samplerate=100000    | 15      | 74      | 52.4     | 0.478 |      |

## 2026-10-14 - local sd-card, dev-version, finalized tuning

| type                            | cpu_min | cpu_max | cpu_mean | MiB/s | note       |
|---------------------------------|---------|---------|----------|-------|------------|
| EMU optimized ShpInput ivtrace  | 39      | 56      | 50.0     | 0.479 |            |
| EMU optimized ShpInput notrace  | 13      | 40      | 23.9     | 0.001 |            |
| EMU optimized hrvformat ivtrace | 11      | 61      | 47.4     | 0.479 |            |
| EMU optimized hrvformat notrace | 12      | 52      | 22.4     | 0.001 |            |
| EMU gpio datarate57600          | 36      | 75      | 49.3     | 0.275 |            |
| EMU gpio datarate115200         | 39      | 100     | 57.5     | 0.361 |            |
| EMU gpio datarate230400         | 50      | 91      | 63.1     | 0.525 |            |
| EMU gpio datarate460800         | 66      | 99      | 77.0     | 0.767 |            |
| EMU gpio datarate921600         | 64      | 100     | 96.1     | 1.131 | high load  |
| EMU gpio datarate1000000        | 69      | 100     | 99.4     | 1.217 | high load  |
| EMU input-option=native+static  | 32      | 56      | 46.6     | 0.198 |            |
| EMU input-option=native+random  | 36      | 63      | 52.5     | 0.479 |            |
| EMU input-option=scaled+static  | 31      | 58      | 43.4     | 0.198 |            |
| EMU input-option=scaled+random  | 34      | 58      | 50.0     | 0.479 |            |
| EMU t_offset=15                 | 56      | 56      | 56.0     | 0.001 | incomplete |
| EMU t_offset=20                 | 36      | 90      | 56.0     | 0.479 | had errors |
| EMU t_offset=25                 | 38      | 62      | 52.8     | 0.479 |            |
| EMU t_offset=30                 | 36      | 64      | 52.7     | 0.479 |            |
| EMU power & samplerate=10       | 13      | 70      | 46.7     | 0.001 |            |
| EMU power & samplerate=100      | 19      | 72      | 48.6     | 0.002 |            |
| EMU power & samplerate=1000     | 11      | 75      | 50.6     | 0.005 |            |
| EMU power & samplerate=100000   | 13      | 77      | 52.2     | 0.360 |            |
| EMU iv & samplerate=10          | 24      | 56      | 38.9     | 0.001 |            |
| EMU iv & samplerate=100         | 24      | 59      | 39.2     | 0.002 |            |
| EMU iv & samplerate=1000        | 24      | 63      | 39.8     | 0.006 |            |
| EMU iv & samplerate=100000      | 36      | 62      | 52.5     | 0.479 |            |
| EMU output-compression=None     | 10      | 66      | 43.4     | 1.528 |            |
| EMU output-compression=lzf      | 34      | 59      | 52.5     | 0.479 |            |
| EMU output-compression=1        | 27      | 63      | 55.0     | 0.408 |            |
| EMU input-compression=None      | 37      | 62      | 52.1     | 0.479 |            |
| EMU input-compression=lzf       | 15      | 67      | 52.2     | 0.479 |            |
| EMU input-compression=1         | 38      | 65      | 54.4     | 0.479 |            |
| HRV t_offset=10                 | 0       | 0       | 0.0      | 0.001 | incomplete |
| HRV t_offset=15                 | 26      | 92      | 40.5     | 0.160 | had errors |
| HRV t_offset=20                 | 28      | 48      | 34.9     | 0.160 |            |
| HRV t_offset=25                 | 28      | 41      | 34.9     | 0.164 |            |
| HRV power & samplerate=10       | 22      | 51      | 35.1     | 0.001 |            |
| HRV power & samplerate=100      | 30      | 45      | 35.9     | 0.001 |            |
| HRV power & samplerate=1000     | 16      | 50      | 36.4     | 0.002 |            |
| HRV power & samplerate=100000   | 30      | 48      | 35.7     | 0.063 |            |
| HRV iv & samplerate=10          | 20      | 38      | 24.9     | 0.001 |            |
| HRV iv & samplerate=100         | 20      | 34      | 24.4     | 0.001 |            |
| HRV iv & samplerate=1000        | 19      | 38      | 24.2     | 0.003 |            |
| HRV iv & samplerate=100000      | 27      | 42      | 34.7     | 0.162 |            |
| HRV compression=None            | 17      | 40      | 28.6     | 1.527 |            |
| HRV compression=lzf             | 26      | 42      | 31.4     | 0.203 |            |
| HRV compression=1               | 27      | 44      | 35.0     | 0.165 |            |

## 2026-10-15 - Testbed, NAS

Learning:

- PTP & PHC2SYS have ~ 10% CPU-Overhead

| type                            | cpu_min | cpu_max | cpu_mean | MiB/s | note      |
|---------------------------------|---------|---------|----------|-------|-----------|
| EMU optimized ShpInput ivtrace  | 25      | 83      | 61.0     | 0.475 |           |
| EMU optimized ShpInput notrace  | 15      | 60      | 34.7     | 0.002 |           |
| EMU optimized hrvformat ivtrace | 31      | 86      | 61.1     | 0.476 |           |
| EMU optimized hrvformat notrace | 23      | 55      | 38.8     | 0.002 |           |
| EMU gpio datarate=57600         | 50      | 95      | 65.2     | 0.310 |           |
| EMU gpio datarate=115200        | 55      | 100     | 70.0     | 0.392 |           |
| EMU gpio datarate=230400        | 65      | 100     | 79.0     | 0.547 |           |
| EMU gpio datarate=460800        | 77      | 100     | 92.7     | 0.787 | high load |
| EMU gpio datarate=921600        | 78      | 100     | 98.9     | 1.146 | high load |
| EMU gpio datarate=1000000       | 77      | 100     | 99.1     | 1.238 | high load |
| EMU input-option=native+static  | 43      | 77      | 59.5     | 0.218 |           |
| EMU input-option=native+random  | 27      | 97      | 65.3     | 0.476 |           |
| EMU input-option=scaled+static  | 25      | 72      | 56.2     | 0.218 |           |
| EMU input-option=scaled+random  | 25      | 92      | 66.8     | 0.476 |           |
| EMU t_offset=20                 | 47      | 100     | 75.1     | 0.476 |           |
| EMU t_offset=25                 | 48      | 100     | 67.1     | 0.476 |           |
| EMU t_offset=30                 | 48      | 90      | 65.1     | 0.476 |           |
| EMU t_offset=35                 | 33      | 100     | 65.3     | 0.477 |           |
| EMU power @ samplerate=10       | 42      | 73      | 59.1     | 0.002 |           |
| EMU power @ samplerate=100      | 33      | 79      | 60.1     | 0.002 |           |
| EMU power @ samplerate=1000     | 49      | 72      | 63.0     | 0.006 |           |
| EMU power @ samplerate=100000   | 48      | 86      | 66.5     | 0.357 |           |
| EMU iv @ samplerate=10          | 35      | 73      | 51.4     | 0.002 |           |
| EMU iv @ samplerate=100         | 37      | 61      | 51.2     | 0.002 |           |
| EMU iv @ samplerate=1000        | 36      | 61      | 51.3     | 0.006 |           |
| EMU iv @ samplerate=100000      | 44      | 96      | 65.9     | 0.477 |           |
| EMU output-compression=None     | 22      | 100     | 61.8     | 1.528 |           |
| EMU output-compression=lzf      | 48      | 94      | 65.1     | 0.477 |           |
| EMU output-compression=1        | 48      | 92      | 69.0     | 0.400 |           |
| EMU input-compression=None      | 41      | 94      | 65.7     | 0.477 |           |
| EMU input-compression=lzf       | 47      | 84      | 65.6     | 0.477 |           |
| EMU input-compression=1         | 50      | 96      | 67.4     | 0.476 |           |
