# Benchmark Results

## 2026-10-07 - testbed

NOTE:
- Shepherd-Sheep v2026.8.1
- Shepherd-Core v2026.7.1

### One Observer to NAS

| type                           | cpu_min | cpu_max | cpu_mean | MiB/s | note               |
|--------------------------------|---------|---------|----------|-------|--------------------|
| EMU optimized ivtrace          | 54      | 100     | 72.5     | 1.087 | had errors, incomplete |
| EMU optimized notrace          | 31      | 100     | 44.5     | 0.002 | incomplete         |
| EMU uart datarate57600         | 63      | 100     | 82.5     | 0.685 |                    |
| EMU uart datarate57600         | 63      | 100     | 82.5     | 0.685 |                    |
| EMU input-option=native+static | 59      | 100     | 73.8     | 0.474 | had errors             |
| EMU input-option=native+random | 52      | 100     | 78.8     | 0.684 | had errors, incomplete |
| EMU input-option=scaled+static | 59      | 100     | 73.4     | 0.475 |                    |
| EMU input-option=scaled+random | 63      | 100     | 79.9     | 0.687 |                    |
| EMU t_offset=15                | 0       | 100     | 88.9     | 0.002 | had errors, incomplete |
| EMU t_offset=20                | 0       | 100     | 89.9     | 0.002 | had errors, incomplete |
| EMU t_offset=25                | 62      | 100     | 86.1     | 0.685 |                    |
| EMU t_offset=30                | 19      | 99      | 77.6     | 0.686 |                    |
| EMU power & samplerate=10      | 47      | 100     | 63.8     | 0.003 | incomplete         |
| EMU power & samplerate=100     | 52      | 93      | 64.3     | 0.003 | incomplete         |
| EMU power & samplerate=1000    | 57      | 100     | 69.5     | 0.010 | incomplete         |
| EMU power & samplerate=100000  | 68      | 100     | 82.8     | 0.501 | incomplete         |
| EMU iv & samplerate=10         | 42      | 88      | 56.7     | 0.003 |                    |
| EMU iv & samplerate=100        | 44      | 100     | 58.6     | 0.003 |                    |
| EMU iv & samplerate=1000       | 44      | 100     | 58.6     | 0.010 |                    |
| EMU iv & samplerate=100000     | 66      | 100     | 79.1     | 0.687 |                    |
| EMU output-compression=None    | 39      | 100     | 59.6     | 1.530 |                    |
| EMU output-compression=lzf     | 56      | 100     | 71.0     | 1.093 |                    |
| EMU output-compression=1       | 64      | 100     | 78.8     | 0.685 | had errors             |
| EMU input-compression=None     | 64      | 100     | 78.2     | 0.687 |                    |
| EMU input-compression=lzf      | 64      | 100     | 80.5     | 0.685 | had errors, incomplete |
| EMU input-compression=1        | 68      | 100     | 90.3     | 0.688 | high load           |

### Local SD-Card

| type                           | cpu_min | cpu_max | cpu_mean | MiB/s | note                         |
|--------------------------------|---------|---------|----------|-------|------------------------------|
| EMU optimized ivtrace          | 60      | 86      | 70.7     | 1.104 |                              |
| EMU optimized notrace          | 27      | 100     | 46.3     | 0.003 |                              |
| EMU uart datarate57600         | 67      | 100     | 82.9     | 0.694 |                              |
| EMU gpio datarate57600         | 76      | 100     | 90.7     | 0.872 | had errors, high load             |
| EMU input-option=native+static | 58      | 100     | 75.0     | 0.476 |                              |
| EMU input-option=native+random | 66      | 100     | 81.5     | 0.694 |                              |
| EMU input-option=scaled+static | 61      | 100     | 75.1     | 0.475 | had errors, incomplete           |
| EMU input-option=scaled+random | 66      | 100     | 80.8     | 0.695 |                              |
| EMU t_offset=15                | 76      | 100     | 96.4     | 0.002 | had errors, incomplete, high load |
| EMU t_offset=20                | 100     | 100     | 100.0    | 0.002 | had errors, incomplete, high load |
| EMU t_offset=25                | 63      | 100     | 81.8     | 0.690 | had errors                       |
| EMU t_offset=30                | 64      | 90      | 79.4     | 0.695 |                              |
| EMU power & samplerate=10      | 52      | 100     | 66.4     | 0.003 | incomplete                   |
| EMU power & samplerate=100     | 52      | 100     | 68.4     | 0.003 | incomplete                   |
| EMU power & samplerate=1000    | 58      | 100     | 72.6     | 0.010 | incomplete                   |
| EMU power & samplerate=100000  | 69      | 100     | 85.0     | 0.508 | incomplete                   |
| EMU iv & samplerate=10         | 42      | 100     | 60.1     | 0.003 |                              |
| EMU iv & samplerate=100        | 44      | 100     | 60.2     | 0.003 |                              |
| EMU iv & samplerate=1000       | 44      | 100     | 61.2     | 0.010 |                              |
| EMU iv & samplerate=100000     | 67      | 100     | 80.8     | 0.695 |                              |
| EMU output-compression=None    | 42      | 100     | 57.9     | 1.525 | had errors, incomplete           |
| EMU output-compression=lzf     | 38      | 100     | 72.6     | 1.102 |                              |
| EMU output-compression=1       | 67      | 100     | 80.8     | 0.693 | had errors                       |
| EMU input-compression=None     | 65      | 100     | 81.1     | 0.693 | had errors, incomplete           |
| EMU input-compression=lzf      | 68      | 100     | 81.5     | 0.693 | had errors                       |
| EMU input-compression=1        | 67      | 100     | 84.3     | 0.695 |                              |

## 2026-10-06 - local sd-card, latest dev-versions

Learnings for us:
- input should be scaled to match gain of PRU
- input & output should be lzf (despite being non-standard-conform)
- min settle time is 15 s
Learnings for the user:
- downsampling is a good idea to increase headroom for GPIO / Uart logging
- turning off power-tracing is also possible
- gpio-traffic can be continuous @ 200 kSps, but also

| type                           | cpu_min | cpu_max | cpu_mean | MiB/s | note                         |
|--------------------------------|---------|---------|----------|-------|------------------------------|
| EMU optimized ivtrace          | 36      | 70      | 50.7     | 0.480 |                              |
| EMU optimized notrace          | 10      | 45      | 15.8     | 0.002 | (REDO after fix)             |
| EMU hrvformat-input ivtrace    | 36      | 60      | 46.9     | 0.435 |                              |
| EMU gpio datarate9600          | 37      | 100     | 52.7     | 0.171 |                              |
| EMU gpio datarate19200         | 37      | 84      | 49.7     | 0.184 |                              |
| EMU gpio datarate57600         | 37      | 86      | 53.6     | 0.237 |                              |
| EMU gpio datarate115200        | 50      | 93      | 61.0     | 0.313 |                              |
| EMU gpio datarate230400        | 63      | 96      | 73.0     | 0.438 |                              |
| EMU gpio datarate460800        | 65      | 100     | 93.5     | 0.653 | high load                     |
| EMU gpio datarate921600        | 86      | 100     | 99.7     | 0.963 | high load                     |
| EMU gpio datarate1000000       | 76      | 100     | 99.4     | 1.034 | high load                     |
| EMU input-option=native+static | 30      | 62      | 48.2     | 0.117 |                              |
| EMU input-option=native+random | 43      | 68      | 56.0     | 0.365 |                              |
| EMU input-option=scaled+static | 35      | 62      | 46.2     | 0.117 |                              |
| EMU input-option=scaled+random | 13      | 80      | 53.6     | 0.365 |                              |
| EMU t_offset=15                | 38      | 67      | 57.2     | 0.365 |                              |
| EMU t_offset=20                | 8       | 74      | 56.4     | 0.365 |                              |
| EMU t_offset=25                | 40      | 66      | 56.8     | 0.365 |                              |
| EMU t_offset=30                | 16      | 74      | 56.1     | 0.365 |                              |
| EMU power & samplerate=10      | 11      | 76      | 45.9     | 0.002 | incomplete                   |
| EMU power & samplerate=100     | 30      | 60      | 46.5     | 0.002 | incomplete                   |
| EMU power & samplerate=1000    | 32      | 60      | 48.0     | 0.006 | incomplete                   |
| EMU power & samplerate=100000  | 67      | 100     | 98.2     | 0.143 | had errors, incomplete, high load |
| EMU iv & samplerate=10         | 26      | 57      | 41.6     | 0.002 |                              |
| EMU iv & samplerate=100        | 26      | 50      | 41.5     | 0.002 |                              |
| EMU iv & samplerate=1000       | 24      | 60      | 41.5     | 0.005 |                              |
| EMU iv & samplerate=100000     | 40      | 64      | 56.3     | 0.365 |                              |
| EMU output-compression=None    | 28      | 66      | 45.6     | 1.529 |                              |
| EMU output-compression=lzf     | 20      | 67      | 54.0     | 0.434 |                              |
| EMU output-compression=1       | 21      | 70      | 56.4     | 0.365 |                              |
| EMU output-compression=6       | 16      | 76      | 64.4     | 0.351 |                              |
| EMU input-compression=None     | 24      | 68      | 55.4     | 0.365 |                              |
| EMU input-compression=lzf      | 39      | 68      | 55.3     | 0.365 |                              |
| EMU input-compression=1        | 39      | 68      | 57.6     | 0.365 |                              |
| EMU input-compression=6        | 9       | 74      | 56.2     | 0.365 |                              |
| HRV t_offset=10                | 28      | 90      | 38.2     | 0.135 | settle longer!               |
| HRV t_offset=15                | 29      | 40      | 34.4     | 0.135 |                              |
| HRV t_offset=20                | 29      | 41      | 34.3     | 0.136 |                              |
| HRV t_offset=25                | 22      | 42      | 33.9     | 0.135 |                              |
| HRV power & samplerate=10      | 24      | 44      | 28.8     | 0.002 | incomplete                   |
| HRV power & samplerate=100     | 24      | 47      | 29.4     | 0.002 | incomplete                   |
| HRV power & samplerate=1000    | 24      | 40      | 30.5     | 0.003 | incomplete                   |
| HRV power & samplerate=100000  | 19      | 100     | 98.7     | 0.036 | incomplete, high load         |
| HRV iv & samplerate=10         | 21      | 48      | 25.0     | 0.002 |                              |
| HRV iv & samplerate=100        | 19      | 40      | 24.7     | 0.002 |                              |
| HRV iv & samplerate=1000       | 20      | 47      | 25.2     | 0.003 |                              |
| HRV iv & samplerate=100000     | 28      | 41      | 34.4     | 0.135 |                              |
| HRV compression=None           | 23      | 39      | 29.4     | 1.529 |                              |
| HRV compression=lzf            | 24      | 47      | 30.8     | 0.174 |                              |
| HRV compression=1              | 27      | 42      | 34.1     | 0.135 |                              |
| HRV compression=6              | 30      | 46      | 38.4     | 0.120 |                              |

## tune gpio-sampling

### baseline (from above)

| type                               | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|------------------------------------|---------|---------|----------|-------|------|
| EMU gpio datarate57600         | 37      | 86      | 53.6     | 0.237 |                              |
| EMU gpio datarate115200        | 50      | 93      | 61.0     | 0.313 |                              |
| EMU gpio datarate230400        | 63      | 96      | 73.0     | 0.438 |                              |
| EMU gpio datarate460800        | 65      | 100     | 93.5     | 0.653 | high load                     |
| EMU gpio datarate921600        | 86      | 100     | 99.7     | 0.963 | high load                     |
| EMU gpio datarate1000000       | 76      | 100     | 99.4     | 1.034 | high load                     |

### chunk=increment, lzf-out, shuffle

| type                               | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|------------------------------------|---------|---------|----------|-------|------|
| EMU optimized ivtrace              | 40 | 62 | 52.9 | 0.480 |  |
| EMU optimized notrace              | 14 | 53 | 23.9 | 0.002 | incomplete |
| EMU hrvformat-input ivtrace        | 39 | 60 | 52.4 | 0.480 |  |
| EMU gpio datarate57600             | 38 | 78 | 53.0 | 0.281 |  |
| EMU gpio datarate115200            | 46 | 89 | 58.8 | 0.371 |  |
| EMU gpio datarate230400            | 54 | 100 | 68.8 | 0.521 |  |
| EMU gpio datarate460800            | 67 | 100 | 85.2 | 0.771 |  |
| EMU gpio datarate921600            | 85 | 100 | 99.8 | 1.128 | high load |
| EMU gpio datarate1000000           | 58 | 100 | 99.3 | 1.228 | high load |

### gpio non-shuffle, iv with 5x increment

| type                               | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|------------------------------------|---------|---------|----------|-------|------|
| EMU optimized ivtrace              | 28 | 62 | 49.5 | 0.480 |  |
| EMU optimized notrace              | 12 | 53 | 23.7 | 0.002 | incomplete |
| EMU hrvformat-input ivtrace        | 37 | 60 | 49.9 | 0.480 |  |
| EMU gpio datarate57600             | 36 | 81 | 50.0 | 0.280 |  |
| EMU gpio datarate115200            | 43 | 94 | 56.8 | 0.369 |  |
| EMU gpio datarate230400            | 52 | 92 | 66.5 | 0.522 |  |
| EMU gpio datarate460800            | 72 | 100 | 83.6 | 0.774 |  |
| EMU gpio datarate921600            | 89 | 100 | 99.8 | 1.127 | high load |
| EMU gpio datarate1000000           | 11 | 100 | 98.4 | 1.227 | high load |

### h5-optimizations, reshape 10x chunk-size

| type                               | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|------------------------------------|---------|---------|----------|-------|------|
| EMU gpio datarate57600             | 32 | 87 | 49.4 | 0.290 |  |
| EMU gpio datarate115200            | 39 | 86 | 54.5 | 0.373 |  |
| EMU gpio datarate230400            | 48 | 90 | 63.9 | 0.520 |  |
| EMU gpio datarate460800            | 65 | 98 | 77.4 | 0.768 |  |
| EMU gpio datarate921600            | 90 | 100 | 99.8 | 1.138 | high load |
| EMU gpio datarate1000000           | 89 | 100 | 99.8 | 1.222 | high load |

### preshape & gpio reshape 100x chunk-size

| type                               | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|------------------------------------|---------|---------|----------|-------|------|
| EMU optimized ivtrace              | 14 | 58 | 47.8 | 0.478 |  |
| EMU optimized notrace              | 8 | 49 | 22.9 | 0.001 | incomplete |
| EMU hrvformat-input ivtrace        | 39 | 55 | 48.6 | 0.478 |  |
| EMU gpio datarate57600             | 34 | 77 | 48.3 | 0.287 |  |
| EMU gpio datarate115200            | 42 | 86 | 53.3 | 0.372 |  |
| EMU gpio datarate230400            | 51 | 92 | 62.3 | 0.519 |  |
| EMU gpio datarate460800            | 66 | 97 | 76.1 | 0.768 |  |
| EMU gpio datarate921600            | 86 | 100 | 96.9 | 1.128 | high load |
| EMU gpio datarate1000000           | 62 | 100 | 99.3 | 1.223 | high load |

## tune resampling performance

### baseline

| type                               | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|------------------------------------|---------|---------|----------|-------|------|
| EMU power & samplerate=10      | 11      | 76      | 45.9     | 0.002 | incomplete                   |
| EMU power & samplerate=100     | 30      | 60      | 46.5     | 0.002 | incomplete                   |
| EMU power & samplerate=1000    | 32      | 60      | 48.0     | 0.006 | incomplete                   |
| EMU power & samplerate=100000  | 67      | 100     | 98.2     | 0.143 | had errors, incomplete, high load |
| EMU iv & samplerate=10         | 26      | 57      | 41.6     | 0.002 |                              |
| EMU iv & samplerate=100        | 26      | 50      | 41.5     | 0.002 |                              |
| EMU iv & samplerate=1000       | 24      | 60      | 41.5     | 0.005 |                              |
| EMU iv & samplerate=100000     | 40      | 64      | 56.3     | 0.365 |                              |

### bugfixes

| type                               | cpu_min | cpu_max | cpu_mean | MiB/s | note |
|------------------------------------|---------|---------|----------|-------|------|
| EMU power & samplerate=10          | 26 | 76 | 48.2 | 0.001 | incomplete |
| EMU power & samplerate=100         | 13 | 70 | 48.1 | 0.002 | incomplete |
| EMU power & samplerate=1000        | 18 | 71 | 51.5 | 0.006 | incomplete |
| EMU power & samplerate=100000      | 39 | 66 | 53.0 | 0.360 | incomplete |
| EMU iv & samplerate=10             | 16 | 76 | 39.2 | 0.001 |  |
| EMU iv & samplerate=100            | 24 | 66 | 39.5 | 0.002 |  |
| EMU iv & samplerate=1000           | 25 | 57 | 39.0 | 0.006 |  |
| EMU iv & samplerate=100000         | 38 | 61 | 52.6 | 0.478 |  |

### stabilize codebase
