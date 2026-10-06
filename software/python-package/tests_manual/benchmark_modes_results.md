# Benchmark Results


## 2026-10-06 - local sd-card, latest dev-versions

| type                          | cpu_min | cpu_max | cpu_mean | note           |
|-------------------------------|---------|---------|----------|----------------|
| EMU t_offset=15               | 40      | 68      | 57.5     | -              |
| EMU t_offset=20               | 38      | 73      | 57.2     | -              |
| EMU t_offset=25               | 35      | 68      | 57.1     | -              |
| EMU t_offset=30               | 38      | 64      | 56.5     | -              |
| EMU power & samplerate=10     | 30      | 65      | 46.6     | -              |
| EMU power & samplerate=100    | 30      | 61      | 46.5     | -              |
| EMU power & samplerate=1000   | 32      | 63      | 47.9     | -              |
| EMU power & samplerate=100000 | 44      | 100     | 97.4     | OVERLOAD       |
| EMU iv & samplerate=10        | 14      | 76      | 41.3     | -              |
| EMU iv & samplerate=100       | 25      | 55      | 41.9     | -              |
| EMU iv & samplerate=1000      | 25      | 60      | 42.1     | -              |
| EMU iv & samplerate=100000    | 40      | 64      | 56.7     | -              |
| EMU output-compression=None   | 30      | 57      | 45.6     | -              |
| EMU output-compression=lzf    | 40      | 70      | 54.1     | -              |
| EMU output-compression=1      | 38      | 70      | 57.8     | -              |
| EMU output-compression=6      | 12      | 76      | 65.0     | -              |
| EMU input-compression=None    | 43      | 66      | 55.4     | -              |
| EMU input-compression=lzf     | 43      | 64      | 55.9     | -              |
| EMU input-compression=1       | 42      | 67      | 57.6     | -              |
| EMU input-compression=6       | 39      | 76      | 58.0     | -              |
| HRV t_offset=10               | 29      | 92      | 38.4     | settle longer! |
| HRV t_offset=15               | 29      | 42      | 34.8     | -              |
| HRV t_offset=20               | 28      | 41      | 34.5     | -              |
| HRV t_offset=25               | 28      | 43      | 34.3     | -              |
| HRV power & samplerate=10     | 23      | 50      | 29.5     | -              |
| HRV power & samplerate=100    | 24      | 41      | 29.1     | -              |
| HRV power & samplerate=1000   | 25      | 45      | 30.7     | -              |
| HRV power & samplerate=100000 | 36      | 100     | 98.9     | OVERLOAD       |
| HRV iv & samplerate=10        | 20      | 47      | 25.4     | -              |
| HRV iv & samplerate=100       | 19      | 42      | 24.9     | -              |
| HRV iv & samplerate=1000      | 20      | 43      | 25.0     | -              |
| HRV iv & samplerate=100000    | 25      | 47      | 35.0     | -              |
| HRV compression=None          | 12      | 55      | 28.9     | -              |
| HRV compression=lzf           | 26      | 40      | 30.7     | -              |
| HRV compression=1             | 28      | 41      | 34.0     | -              |
| HRV compression=6             | 31      | 45      | 38.4     | -              |
