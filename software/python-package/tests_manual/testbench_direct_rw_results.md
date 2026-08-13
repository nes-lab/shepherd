# Benchmarking the File-OP-Pipeline

Essential parts are taken from shepherd-codebase and can be benchmarked here.
Its also a playground for new ideas and tracking changes (improvements and regressions) for later software versions.

## Learnings

- h5py.directRW() does not make things faster for us -> plus code-quality is worse
- switching to lzf and omitting timestamp -> each brings 30% improvement -> adds up to ~50%
- worst case (var I & V, plus reading) can DOS the BBB with 117% load without writing any gpio

## BBB 2026-06

Software versions

```
python             3.11.2

h5py               3.16.0
    hdf5-tools     1.10.8 (currently v2.1 is out)
numpy              2.4.6
pydantic           2.13.4
pydantic_core      2.46.4
```

Results

```
RUN with duration 60 s, compression Compression.lzf, random False
        Old F2RAM = 4.024000 s, RAM2F = 17.988000 s
        New F2RAM = 4.018000 s, RAM2F = 8.372000 s, RAM2Fts = 20.067000
        Size f_in = 51.238000 MB, f_old = 51.243000 MB, f_new = 21.727000 MB, f_nts = 51.243000 MB
RUN with duration 60 s, compression Compression.gzip1, random False
        Old F2RAM = 5.960000 s, RAM2F = 21.154000 s
        New F2RAM = 5.092000 s, RAM2F = 10.553000 s, RAM2Fts = 23.134000
        Size f_in = 25.203000 MB, f_old = 25.205000 MB, f_new = 9.858000 MB, f_nts = 25.205000 MB
RUN with duration 60 s, compression Compression.null, random False
        Old F2RAM = 2.970000 s, RAM2F = 11.593000 s
        New F2RAM = 4.319000 s, RAM2F = 7.033000 s, RAM2Fts = 13.829000
        Size f_in = 91.632000 MB, f_old = 91.632000 MB, f_new = 45.832000 MB, f_nts = 91.632000 MB
RUN with duration 60 s, compression Compression.lzf, random True
        Old F2RAM = 3.588000 s, RAM2F = 26.893000 s
        New F2RAM = 3.615000 s, RAM2F = 17.792000 s, RAM2Fts = 28.412000
        Size f_in = 75.343000 MB, f_old = 75.349000 MB, f_new = 45.832000 MB, f_nts = 75.349000 MB
RUN with duration 60 s, compression Compression.gzip1, random True
        Old F2RAM = 6.777000 s, RAM2F = 29.791000 s
        New F2RAM = 5.872000 s, RAM2F = 19.564000 s, RAM2Fts = 31.369000
        Size f_in = 59.797000 MB, f_old = 59.799000 MB, f_new = 44.452000 MB, f_nts = 59.799000 MB
RUN with duration 60 s, compression Compression.null, random True
        Old F2RAM = 2.988000 s, RAM2F = 10.646000 s
        New F2RAM = 3.531000 s, RAM2F = 5.849000 s, RAM2Fts = 13.169000
        Size f_in = 91.632000 MB, f_old = 91.632000 MB, f_new = 45.832000 MB, f_nts = 91.632000 MB
```

Analysis

- compared to 2023, the performance almost doubled in most benchmarks.
- when IO to storage is not bottlenecked, it is recommended to store data without compression for the highest throughput
- new RAM2F has advantages against old version

## BBB 2023-12

```
RUN with duration 60 s, compression lzf, random False
    Old F2RAM = 8.26 s, RAM2F = 25.749 s
    New F2RAM = 8.622 s, RAM2F = 15.615 s, RAM2Fts = 33.543
    Size f_in = 51.24 MB,  f_old = 51.252 MB,  f_new = 21.729 MB,  f_nts = 51.252 MB
RUN with duration 60 s, compression 1, random False
    Old F2RAM = 8.602 s, RAM2F = 37.842 s
    New F2RAM = 10.632 s, RAM2F = 19.224 s, RAM2Fts = 41.972
    Size f_in = 25.203 MB,  f_old = 25.205 MB,  f_new = 9.859 MB,  f_nts = 25.205 MB
RUN with duration 60 s, compression None, random False
    Old F2RAM = 3.863 s, RAM2F = 19.868 s
    New F2RAM = 8.583 s, RAM2F = 9.899 s, RAM2Fts = 24.901
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
RUN with duration 60 s, compression lzf, random True
    Old F2RAM = 7.468 s, RAM2F = 39.102 s
    New F2RAM = 4.053 s, RAM2F = 28.189 s, RAM2Fts = 45.096
    Size f_in = 75.344 MB,  f_old = 75.356 MB,  f_new = 45.832 MB,  f_nts = 75.356 MB
RUN with duration 60 s, compression 1, random True
    Old F2RAM = 12.998 s, RAM2F = 57.463 s
    New F2RAM = 6.396 s, RAM2F = 36.602 s, RAM2Fts = 60.689
    Size f_in = 59.797 MB,  f_old = 59.799 MB,  f_new = 44.452 MB,  f_nts = 59.799 MB
RUN with duration 60 s, compression None, random True
    Old F2RAM = 6.494 s, RAM2F = 24.419 s
    New F2RAM = 5.027 s, RAM2F = 11.391 s, RAM2Fts = 25.679
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
```

## BB AI 64 2023-12

```
RUN with duration 60 s, compression lzf, random False
    Old F2RAM = 0.596 s, RAM2F = 2.383 s
    New F2RAM = 0.486 s, RAM2F = 1.262 s, RAM2Fts = 2.502
    Size f_in = 51.24 MB,  f_old = 51.252 MB,  f_new = 21.729 MB,  f_nts = 51.252 MB
RUN with duration 60 s, compression 1, random False
    Old F2RAM = 0.868 s, RAM2F = 3.767 s
    New F2RAM = 0.636 s, RAM2F = 1.851 s, RAM2Fts = 3.819
    Size f_in = 25.203 MB,  f_old = 25.205 MB,  f_new = 9.859 MB,  f_nts = 25.205 MB
RUN with duration 60 s, compression None, random False
    Old F2RAM = 0.331 s, RAM2F = 2.155 s
    New F2RAM = 0.374 s, RAM2F = 1.184 s, RAM2Fts = 1.514
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
RUN with duration 60 s, compression lzf, random True
    Old F2RAM = 0.521 s, RAM2F = 3.011 s
    New F2RAM = 0.384 s, RAM2F = 1.922 s, RAM2Fts = 4.538
    Size f_in = 75.344 MB,  f_old = 75.356 MB,  f_new = 45.832 MB,  f_nts = 75.356 MB
RUN with duration 60 s, compression 1, random True
    Old F2RAM = 1.031 s, RAM2F = 5.732 s
    New F2RAM = 0.828 s, RAM2F = 3.852 s, RAM2Fts = 5.841
    Size f_in = 59.797 MB,  f_old = 59.799 MB,  f_new = 44.452 MB,  f_nts = 59.799 MB
RUN with duration 60 s, compression None, random True
    Old F2RAM = 0.334 s, RAM2F = 1.41 s
    New F2RAM = 0.385 s, RAM2F = 0.849 s, RAM2Fts = 1.529
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
```
