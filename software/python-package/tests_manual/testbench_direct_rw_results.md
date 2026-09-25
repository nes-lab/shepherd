# Benchmarking the File-OP-Pipeline

Essential parts are taken from shepherd-codebase and can be benchmarked here.
It's also a playground for new ideas and tracking changes (improvements and regressions) for later software versions.

## Learnings

- h5py.directRW() does not make things faster for us -> plus code-quality is worse
- ~~switching to lzf and omitting timestamp -> each brings 30% improvement -> adds up to ~50%
- worst case (var I & V, plus reading) can DOS the BBB with 117% load without writing any gpio
- gzip got a lot faster over the years - overhead is acceptable
  - even loading harvesting traces with gzip6 comes with no mayor penalty

## BBB 2026-09-25

Mayor changes: kernel 6.12.109 & 6.18.52

```
RUN with duration 60 s, Compression.null, random False
        Old F2RAM = 3.802 s, RAM2F = 10.507 s
        New F2RAM = 6.653 s, RAM2F = 5.690 s, RAM2Fts = 13.013
        Size f_in = 91.632 MB, f_old = 91.632 MB, f_new = 45.832 MB, f_nts = 91.632 MB
RUN with duration 60 s, Compression.lzf, random False
        Old F2RAM = 3.806 s, RAM2F = 10.411 s
        New F2RAM = 3.712 s, RAM2F = 5.752 s, RAM2Fts = 12.327
        Size f_in = 6.078 MB, f_old = 6.035 MB, f_new = 2.632 MB, f_nts = 6.035 MB
RUN with duration 60 s, Compression.gzip1, random False
        Old F2RAM = 4.695 s, RAM2F = 12.146 s
        New F2RAM = 4.304 s, RAM2F = 6.501 s, RAM2Fts = 13.996
        Size f_in = 4.165 MB, f_old = 4.161 MB, f_new = 1.964 MB, f_nts = 4.161 MB
RUN with duration 60 s, Compression.gzip6, random False
        Old F2RAM = 4.722 s, RAM2F = 14.267 s
        New F2RAM = 4.463 s, RAM2F = 7.591 s, RAM2Fts = 16.138
        Size f_in = 2.937 MB, f_old = 2.940 MB, f_new = 1.409 MB, f_nts = 2.940 MB
RUN with duration 60 s, Compression.null, random True
        Old F2RAM = 3.807 s, RAM2F = 10.060 s
        New F2RAM = 6.639 s, RAM2F = 6.680 s, RAM2Fts = 18.100
        Size f_in = 91.632 MB, f_old = 91.632 MB, f_new = 45.832 MB, f_nts = 91.632 MB
RUN with duration 60 s, Compression.lzf, random True
        Old F2RAM = 4.081 s, RAM2F = 19.674 s
        New F2RAM = 4.030 s, RAM2F = 15.316 s, RAM2Fts = 21.848
        Size f_in = 48.613 MB, f_old = 48.570 MB, f_new = 45.166 MB, f_nts = 48.570 MB
RUN with duration 60 s, Compression.gzip1, random True
        Old F2RAM = 5.651 s, RAM2F = 21.150 s
        New F2RAM = 5.307 s, RAM2F = 15.540 s, RAM2Fts = 23.022
        Size f_in = 44.843 MB, f_old = 44.839 MB, f_new = 42.642 MB, f_nts = 44.839 MB
RUN with duration 60 s, Compression.gzip6, random True
        Old F2RAM = 5.453 s, RAM2F = 23.367 s
        New F2RAM = 5.279 s, RAM2F = 16.802 s, RAM2Fts = 25.532
        Size f_in = 44.062 MB, f_old = 44.064 MB, f_new = 42.533 MB, f_nts = 44.064 MB
```

## BBB 2026-09-21

Mayor changes: active shuffle for datasets and optimized chunking for timestamps

```
RUN with duration 60 s, Compression.null, random False
        Old F2RAM = 3.882 s, RAM2F = 12.330 s
        New F2RAM = 5.589 s, RAM2F = 6.717 s, RAM2Fts = 13.437
        Size f_in = 91.632 MB, f_old = 91.632 MB, f_new = 45.832 MB, f_nts = 91.632 MB
RUN with duration 60 s, Compression.lzf, random False
        Old F2RAM = 3.994 s, RAM2F = 10.913 s
        New F2RAM = 3.855 s, RAM2F = 6.066 s, RAM2Fts = 12.831
        Size f_in = 6.078 MB, f_old = 6.035 MB, f_new = 2.632 MB, f_nts = 6.035 MB
RUN with duration 60 s, Compression.gzip1, random False
        Old F2RAM = 4.901 s, RAM2F = 12.583 s
        New F2RAM = 4.470 s, RAM2F = 6.769 s, RAM2Fts = 14.556
        Size f_in = 4.165 MB, f_old = 4.161 MB, f_new = 1.964 MB, f_nts = 4.161 MB
RUN with duration 60 s, Compression.gzip6, random False
        Old F2RAM = 4.947 s, RAM2F = 14.875 s
        New F2RAM = 4.689 s, RAM2F = 7.853 s, RAM2Fts = 16.723
        Size f_in = 2.937 MB, f_old = 2.940 MB, f_new = 1.409 MB, f_nts = 2.940 MB
RUN with duration 60 s, Compression.null, random True
        Old F2RAM = 3.886 s, RAM2F = 11.226 s
        New F2RAM = 3.873 s, RAM2F = 7.430 s, RAM2Fts = 14.994
        Size f_in = 91.632 MB, f_old = 91.632 MB, f_new = 45.832 MB, f_nts = 91.632 MB
RUN with duration 60 s, Compression.lzf, random True
        Old F2RAM = 4.231 s, RAM2F = 20.715 s
        New F2RAM = 4.180 s, RAM2F = 16.110 s, RAM2Fts = 22.892
        Size f_in = 48.611 MB, f_old = 48.568 MB, f_new = 45.164 MB, f_nts = 48.568 MB
RUN with duration 60 s, Compression.gzip1, random True
        Old F2RAM = 5.932 s, RAM2F = 22.650 s
        New F2RAM = 5.484 s, RAM2F = 16.898 s, RAM2Fts = 24.236
        Size f_in = 44.843 MB, f_old = 44.839 MB, f_new = 42.642 MB, f_nts = 44.839 MB
RUN with duration 60 s, Compression.gzip6, random True
        Old F2RAM = 5.847 s, RAM2F = 24.561 s
        New F2RAM = 5.468 s, RAM2F = 18.450 s, RAM2Fts = 27.146
        Size f_in = 44.063 MB, f_old = 44.065 MB, f_new = 42.534 MB, f_nts = 44.065 MB
```

Conclusion:
- 20-50 % less time needed for storing
- smaller files
- tested kernel 4.19 and 6.1 with similar performance
- ~~kernel 6.12-ti seems to be more busy and shows 10 % worse results
  - that one seems broken (use -bone version)

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
RUN with duration 60 s, Compression.null, random False
        Old F2RAM = 2.970 s, RAM2F = 11.593 s
        New F2RAM = 4.319 s, RAM2F = 7.033 s, RAM2Fts = 13.829
        Size f_in = 91.632 MB, f_old = 91.632 MB, f_new = 45.832 MB, f_nts = 91.632 MB
RUN with duration 60 s, Compression.lzf, random False
        Old F2RAM = 4.024 s, RAM2F = 17.988 s
        New F2RAM = 4.018 s, RAM2F = 8.372 s, RAM2Fts = 20.067
        Size f_in = 51.238 MB, f_old = 51.243 MB, f_new = 21.727 MB, f_nts = 51.243 MB
RUN with duration 60 s, Compression.gzip1, random False
        Old F2RAM = 5.960 s, RAM2F = 21.154 s
        New F2RAM = 5.092 s, RAM2F = 10.553 s, RAM2Fts = 23.134
        Size f_in = 25.203 MB, f_old = 25.205 MB, f_new = 9.858 MB, f_nts = 25.205 MB
RUN with duration 60 s, Compression.null, random True
        Old F2RAM = 2.988 s, RAM2F = 10.646 s
        New F2RAM = 3.531 s, RAM2F = 5.849 s, RAM2Fts = 13.169
        Size f_in = 91.632 MB, f_old = 91.632 MB, f_new = 45.832 MB, f_nts = 91.632 MB
RUN with duration 60 s, Compression.lzf, random True
        Old F2RAM = 3.588 s, RAM2F = 26.893 s
        New F2RAM = 3.615 s, RAM2F = 17.792 s, RAM2Fts = 28.412
        Size f_in = 75.343 MB, f_old = 75.349 MB, f_new = 45.832 MB, f_nts = 75.349 MB
RUN with duration 60 s, Compression.gzip1, random True
        Old F2RAM = 6.777 s, RAM2F = 29.791 s
        New F2RAM = 5.872 s, RAM2F = 19.564 s, RAM2Fts = 31.369
        Size f_in = 59.797 MB, f_old = 59.799 MB, f_new = 44.452 MB, f_nts = 59.799 MB
```

Analysis

- compared to 2023, the performance almost doubled in most benchmarks.
- when IO to storage is not bottlenecked, it is recommended to store data without compression for the highest throughput
- new RAM2F has advantages against old version

## BBB 2023-12

```
RUN with duration 60 s, Compression.None, random False
    Old F2RAM = 3.863 s, RAM2F = 19.868 s
    New F2RAM = 8.583 s, RAM2F = 9.899 s, RAM2Fts = 24.901
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
RUN with duration 60 s, Compression.lzf, random False
    Old F2RAM = 8.26 s, RAM2F = 25.749 s
    New F2RAM = 8.622 s, RAM2F = 15.615 s, RAM2Fts = 33.543
    Size f_in = 51.24 MB,  f_old = 51.252 MB,  f_new = 21.729 MB,  f_nts = 51.252 MB
RUN with duration 60 s, Compression.gzip1, random False
    Old F2RAM = 8.602 s, RAM2F = 37.842 s
    New F2RAM = 10.632 s, RAM2F = 19.224 s, RAM2Fts = 41.972
    Size f_in = 25.203 MB,  f_old = 25.205 MB,  f_new = 9.859 MB,  f_nts = 25.205 MB
RUN with duration 60 s, Compression.None, random True
    Old F2RAM = 6.494 s, RAM2F = 24.419 s
    New F2RAM = 5.027 s, RAM2F = 11.391 s, RAM2Fts = 25.679
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
RUN with duration 60 s, Compression.lzf, random True
    Old F2RAM = 7.468 s, RAM2F = 39.102 s
    New F2RAM = 4.053 s, RAM2F = 28.189 s, RAM2Fts = 45.096
    Size f_in = 75.344 MB,  f_old = 75.356 MB,  f_new = 45.832 MB,  f_nts = 75.356 MB
RUN with duration 60 s, Compression.gzip1, random True
    Old F2RAM = 12.998 s, RAM2F = 57.463 s
    New F2RAM = 6.396 s, RAM2F = 36.602 s, RAM2Fts = 60.689
    Size f_in = 59.797 MB,  f_old = 59.799 MB,  f_new = 44.452 MB,  f_nts = 59.799 MB
```

## BB AI 64 2023-12

```
RUN with duration 60 s, Compression.None, random False
    Old F2RAM = 0.331 s, RAM2F = 2.155 s
    New F2RAM = 0.374 s, RAM2F = 1.184 s, RAM2Fts = 1.514
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
RUN with duration 60 s, Compression.lzf, random False
    Old F2RAM = 0.596 s, RAM2F = 2.383 s
    New F2RAM = 0.486 s, RAM2F = 1.262 s, RAM2Fts = 2.502
    Size f_in = 51.24 MB,  f_old = 51.252 MB,  f_new = 21.729 MB,  f_nts = 51.252 MB
RUN with duration 60 s, Compression.gzip1, random False
    Old F2RAM = 0.868 s, RAM2F = 3.767 s
    New F2RAM = 0.636 s, RAM2F = 1.851 s, RAM2Fts = 3.819
    Size f_in = 25.203 MB,  f_old = 25.205 MB,  f_new = 9.859 MB,  f_nts = 25.205 MB
RUN with duration 60 s, Compression.None, random True
    Old F2RAM = 0.334 s, RAM2F = 1.41 s
    New F2RAM = 0.385 s, RAM2F = 0.849 s, RAM2Fts = 1.529
    Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
RUN with duration 60 s, Compression.lzf, random True
    Old F2RAM = 0.521 s, RAM2F = 3.011 s
    New F2RAM = 0.384 s, RAM2F = 1.922 s, RAM2Fts = 4.538
    Size f_in = 75.344 MB,  f_old = 75.356 MB,  f_new = 45.832 MB,  f_nts = 75.356 MB
RUN with duration 60 s, Compression.gzip1, random True
    Old F2RAM = 1.031 s, RAM2F = 5.732 s
    New F2RAM = 0.828 s, RAM2F = 3.852 s, RAM2Fts = 5.841
    Size f_in = 59.797 MB,  f_old = 59.799 MB,  f_new = 44.452 MB,  f_nts = 59.799 MB
```
