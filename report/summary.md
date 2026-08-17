# parmar sweep analysis

452 result rows, **452 round-trip verified**, 0 not verified.  Tiers present: 64MB, 256MB, 1GB, 4GB


## Tier 64MB

### Best compression ratio (archival)

| ratio  | bytes      | pipeline            | backend           | transport          | threads | MB/s |
|--------|------------|---------------------|-------------------|--------------------|---------|------|
| 3.9304 | 17,101,861 | p50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli     | 20      | 2.95 |
| 3.9214 | 17,141,189 | r50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli     | 20      | 2.77 |
| 3.9061 | 17,208,333 | p50k_base+fixed_u16 | lzma_fast         | subprocess_cli     | 20      | 2.93 |
| 3.9060 | 17,209,016 | p50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.98 |
| 3.8975 | 17,246,460 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 1       | 2.41 |
| 3.8975 | 17,246,464 | r50k_base+fixed_u16 | lzma_extreme      | in_process_binding | 20      | 2.77 |
| 3.8975 | 17,246,468 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.84 |
| 3.8975 | 17,246,468 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 4       | 2.70 |
| 3.8975 | 17,246,468 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.84 |
| 3.8975 | 17,246,468 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.81 |

### Best throughput (interactive)

| MB/s  | ratio  | pipeline            | backend | transport          | threads | peak_rss_mb |
|-------|--------|---------------------|---------|--------------------|---------|-------------|
| 34.49 | 3.1348 | raw                 | zstd_12 | subprocess_cli     | 20      | 262         |
| 34.17 | 3.1348 | raw                 | zstd_12 | subprocess_cli     | 20      | 262         |
| 34.11 | 3.1348 | raw                 | zstd_12 | subprocess_cli     | 4       | 262         |
| 33.76 | 3.1348 | raw                 | zstd_12 | subprocess_cli     | 20      | 262         |
| 33.43 | 3.1348 | raw                 | zstd_12 | subprocess_cli     | 20      | 262         |
| 25.69 | 3.1348 | raw                 | zstd_12 | in_process_binding | 20      | 295         |
| 23.62 | 3.3186 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli     | 20      | 1002        |
| 23.50 | 3.3186 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli     | 20      | 1060        |
| 23.26 | 3.3162 | o200k_base+leb128   | zstd_12 | subprocess_cli     | 20      | 1494        |
| 23.24 | 3.3266 | p50k_base+fixed_u16 | zstd_12 | subprocess_cli     | 20      | 960         |


## Tier 256MB

### Best compression ratio (archival)

| ratio  | bytes      | pipeline            | backend           | transport          | threads | MB/s |
|--------|------------|---------------------|-------------------|--------------------|---------|------|
| 4.0488 | 66,316,481 | p50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli     | 20      | 2.49 |
| 4.0434 | 66,405,748 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 1       | 1.85 |
| 4.0434 | 66,405,752 | r50k_base+fixed_u16 | lzma_extreme      | in_process_binding | 20      | 2.06 |
| 4.0344 | 66,553,385 | r50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli     | 20      | 2.56 |
| 4.0295 | 66,635,504 | p50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.50 |
| 4.0152 | 66,872,072 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.53 |
| 4.0152 | 66,872,072 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 4       | 2.25 |
| 4.0152 | 66,872,072 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.33 |
| 4.0152 | 66,872,072 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.34 |
| 4.0152 | 66,872,072 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli     | 20      | 2.33 |

### Best throughput (interactive)

| MB/s  | ratio  | pipeline            | backend | transport      | threads | peak_rss_mb |
|-------|--------|---------------------|---------|----------------|---------|-------------|
| 71.54 | 3.1627 | raw                 | zstd_12 | subprocess_cli | 20      | 756         |
| 68.32 | 3.1627 | raw                 | zstd_12 | subprocess_cli | 20      | 755         |
| 66.81 | 3.1627 | raw                 | zstd_12 | subprocess_cli | 20      | 755         |
| 66.34 | 3.1627 | raw                 | zstd_12 | subprocess_cli | 20      | 755         |
| 65.82 | 3.1627 | raw                 | zstd_12 | subprocess_cli | 20      | 755         |
| 51.12 | 3.1627 | raw                 | zstd_12 | subprocess_cli | 4       | 490         |
| 34.59 | 3.3650 | p50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 3979        |
| 34.23 | 3.3604 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 4060        |
| 33.15 | 3.3604 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 4953        |
| 32.78 | 3.3604 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 2153        |


## Tier 1GB

### Best compression ratio (archival)

| ratio  | bytes       | pipeline            | backend           | transport      | threads | MB/s  |
|--------|-------------|---------------------|-------------------|----------------|---------|-------|
| 4.1015 | 262,101,876 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 1       | 1.60  |
| 4.0855 | 263,129,045 | p50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli | 20      | 7.88  |
| 4.0668 | 264,335,564 | p50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 20      | 7.83  |
| 4.0661 | 264,379,209 | r50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli | 20      | 7.99  |
| 4.0480 | 265,566,924 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 20      | 7.97  |
| 4.0480 | 265,566,924 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 4       | 5.80  |
| 4.0369 | 266,294,009 | r50k_base+fixed_u16 | lzma_fast         | subprocess_cli | 1       | 1.78  |
| 4.0037 | 268,504,437 | p50k_base+fixed_u16 | lzma_fast         | subprocess_cli | 20      | 14.12 |
| 3.9811 | 270,029,253 | r50k_base+fixed_u16 | lzma_fast         | subprocess_cli | 20      | 14.19 |
| 3.9811 | 270,029,253 | r50k_base+fixed_u16 | lzma_fast         | subprocess_cli | 4       | 5.83  |

### Best throughput (interactive)

| MB/s  | ratio  | pipeline            | backend | transport      | threads | peak_rss_mb |
|-------|--------|---------------------|---------|----------------|---------|-------------|
| 79.02 | 3.1825 | raw                 | zstd_12 | subprocess_cli | 20      | 1831        |
| 52.27 | 3.1825 | raw                 | zstd_12 | subprocess_cli | 4       | 492         |
| 39.04 | 3.3905 | p50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 4610        |
| 38.97 | 3.3800 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 4712        |
| 34.34 | 3.3779 | o200k_base+leb128   | zstd_12 | subprocess_cli | 20      | 6523        |
| 30.00 | 3.3986 | cl100k_base+leb128  | zstd_12 | subprocess_cli | 20      | 6496        |
| 29.76 | 3.3560 | p50k_base+leb128    | zstd_12 | subprocess_cli | 20      | 6747        |
| 29.17 | 3.3455 | r50k_base+leb128    | zstd_12 | subprocess_cli | 20      | 6994        |
| 28.07 | 3.3779 | o200k_base+leb128   | zstd_12 | subprocess_cli | 4       | 6462        |
| 25.24 | 3.3800 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli | 4       | 4515        |


## Tier 4GB

### Best compression ratio (archival)

| ratio  | bytes         | pipeline            | backend           | transport      | threads | MB/s  |
|--------|---------------|---------------------|-------------------|----------------|---------|-------|
| 4.0984 | 1,048,037,140 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 1       | 1.79  |
| 4.0785 | 1,053,147,357 | p50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli | 20      | 16.26 |
| 4.0634 | 1,057,067,001 | r50k_base+fixed_u16 | lzma_tuned_lp1pb1 | subprocess_cli | 20      | 17.44 |
| 4.0602 | 1,057,885,412 | p50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 20      | 15.82 |
| 4.0454 | 1,061,753,144 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 20      | 16.88 |
| 4.0454 | 1,061,753,144 | r50k_base+fixed_u16 | lzma_extreme      | subprocess_cli | 4       | 7.09  |
| 4.0284 | 1,066,252,857 | r50k_base+fixed_u16 | lzma_fast         | subprocess_cli | 1       | 1.97  |
| 4.0001 | 1,073,779,078 | p50k_base+fixed_u16 | zstd_22_long      | subprocess_cli | 20      | 5.60  |
| 3.9928 | 1,075,755,361 | p50k_base+fixed_u16 | lzma_fast         | subprocess_cli | 20      | 19.81 |
| 3.9841 | 1,078,089,799 | r50k_base+fixed_u16 | zstd_22_long      | subprocess_cli | 20      | 6.20  |

### Best throughput (interactive)

| MB/s  | ratio  | pipeline            | backend | transport      | threads | peak_rss_mb |
|-------|--------|---------------------|---------|----------------|---------|-------------|
| 76.19 | 3.1740 | raw                 | zstd_12 | subprocess_cli | 20      | 1842        |
| 52.16 | 3.1740 | raw                 | zstd_12 | subprocess_cli | 4       | 502         |
| 39.83 | 3.3722 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 5104        |
| 38.48 | 3.3814 | p50k_base+fixed_u16 | zstd_12 | subprocess_cli | 20      | 5110        |
| 36.50 | 3.3700 | o200k_base+leb128   | zstd_12 | subprocess_cli | 20      | 7119        |
| 31.00 | 3.3700 | o200k_base+leb128   | zstd_12 | subprocess_cli | 4       | 6504        |
| 30.78 | 3.3898 | cl100k_base+leb128  | zstd_12 | subprocess_cli | 20      | 7128        |
| 29.96 | 3.3371 | r50k_base+leb128    | zstd_12 | subprocess_cli | 20      | 7476        |
| 28.52 | 3.3466 | p50k_base+leb128    | zstd_12 | subprocess_cli | 20      | 7365        |
| 26.83 | 3.3722 | r50k_base+fixed_u16 | zstd_12 | subprocess_cli | 4       | 4586        |


## Section 7 part 4 -- the four questions

### Q1. Does the parmar/raw-backend ratio gap grow with corpus size?

Ratio gap = parmar ratio - the same backend's raw-bytes ratio, at each tier, shown absolute and as a percentage of the raw ratio. `trend` is the change from the smallest tier to the largest; the verdict is judged on the *relative* gap in percentage points, since absolute ratios rise with corpus size regardless.

| backend           | pipeline            | 64MB             | 256MB            | 1GB              | 4GB              | trend            | verdict |
|-------------------|---------------------|------------------|------------------|------------------|------------------|------------------|---------|
| bz2_9             | cl100k_base+leb128  | -0.1442 (-4.1%)  | -0.1434 (-4.0%)  | -0.1413 (-4.0%)  | -0.1395 (-3.9%)  | +0.0046 (+0.2pp) | flat    |
| bz2_9             | o200k_base+leb128   | -0.1721 (-4.9%)  | -0.1760 (-5.0%)  | -0.1741 (-4.9%)  | -0.1731 (-4.9%)  | -0.0010 (+0.0pp) | flat    |
| bz2_9             | p50k_base+fixed_u16 | -0.1364 (-3.9%)  | -0.1385 (-3.9%)  | -0.1365 (-3.8%)  | -0.1371 (-3.9%)  | -0.0007 (+0.0pp) | flat    |
| bz2_9             | p50k_base+leb128    | -0.1131 (-3.2%)  | -0.1090 (-3.1%)  | -0.1088 (-3.1%)  | -0.1082 (-3.0%)  | +0.0049 (+0.2pp) | flat    |
| bz2_9             | r50k_base+fixed_u16 | -0.1401 (-4.0%)  | -0.1440 (-4.1%)  | -0.1427 (-4.0%)  | -0.1420 (-4.0%)  | -0.0019 (-0.0pp) | flat    |
| bz2_9             | r50k_base+leb128    | -0.1068 (-3.0%)  | -0.1125 (-3.2%)  | -0.1112 (-3.1%)  | -0.1120 (-3.1%)  | -0.0052 (-0.1pp) | flat    |
| gzip_9            | cl100k_base+leb128  | +0.2831 (+10.6%) | +0.2834 (+10.6%) | +0.2882 (+10.7%) | +0.2875 (+10.7%) | +0.0044 (+0.1pp) | flat    |
| gzip_9            | o200k_base+leb128   | +0.2436 (+9.2%)  | +0.2443 (+9.1%)  | +0.2486 (+9.2%)  | +0.2481 (+9.2%)  | +0.0045 (+0.1pp) | flat    |
| gzip_9            | p50k_base+fixed_u16 | +0.4093 (+15.4%) | +0.4085 (+15.2%) | +0.4130 (+15.3%) | +0.4115 (+15.3%) | +0.0021 (-0.1pp) | flat    |
| gzip_9            | p50k_base+leb128    | +0.3186 (+12.0%) | +0.3189 (+11.9%) | +0.3234 (+12.0%) | +0.3221 (+12.0%) | +0.0035 (+0.0pp) | flat    |
| gzip_9            | r50k_base+fixed_u16 | +0.4024 (+15.1%) | +0.4014 (+15.0%) | +0.4052 (+15.0%) | +0.4033 (+15.0%) | +0.0009 (-0.1pp) | flat    |
| gzip_9            | r50k_base+leb128    | +0.3128 (+11.8%) | +0.3129 (+11.7%) | +0.3169 (+11.8%) | +0.3152 (+11.7%) | +0.0024 (-0.0pp) | flat    |
| lzma_extreme      | cl100k_base+leb128  | +0.0613 (+1.7%)  | +0.1277 (+3.4%)  | +0.1289 (+3.5%)  | +0.1296 (+3.5%)  | +0.0683 (+1.8pp) | WIDENS  |
| lzma_extreme      | o200k_base+leb128   | +0.0363 (+1.0%)  | +0.1015 (+2.7%)  | +0.1036 (+2.8%)  | +0.1057 (+2.8%)  | +0.0694 (+1.8pp) | WIDENS  |
| lzma_extreme      | p50k_base+fixed_u16 | +0.2741 (+7.5%)  | +0.3178 (+8.6%)  | +0.3336 (+8.9%)  | +0.3381 (+9.1%)  | +0.0640 (+1.5pp) | WIDENS  |
| lzma_extreme      | p50k_base+leb128    | +0.0597 (+1.6%)  | +0.0982 (+2.6%)  | +0.1084 (+2.9%)  | +0.1134 (+3.0%)  | +0.0537 (+1.4pp) | WIDENS  |
| lzma_extreme      | r50k_base+fixed_u16 | +0.2657 (+7.3%)  | +0.3035 (+8.2%)  | +0.3148 (+8.4%)  | +0.3233 (+8.7%)  | +0.0577 (+1.4pp) | WIDENS  |
| lzma_extreme      | r50k_base+leb128    | +0.0538 (+1.5%)  | +0.0861 (+2.3%)  | +0.0929 (+2.5%)  | +0.1021 (+2.7%)  | +0.0483 (+1.3pp) | WIDENS  |
| lzma_fast         | cl100k_base+leb128  | +0.0822 (+2.3%)  | +0.1292 (+3.5%)  | +0.1294 (+3.5%)  | +0.1287 (+3.5%)  | +0.0465 (+1.2pp) | WIDENS  |
| lzma_fast         | o200k_base+leb128   | +0.0573 (+1.6%)  | +0.1016 (+2.8%)  | +0.1037 (+2.8%)  | +0.1033 (+2.8%)  | +0.0460 (+1.2pp) | WIDENS  |
| lzma_fast         | p50k_base+fixed_u16 | +0.2947 (+8.2%)  | +0.3232 (+8.9%)  | +0.3379 (+9.2%)  | +0.3367 (+9.2%)  | +0.0419 (+1.0pp) | WIDENS  |
| lzma_fast         | p50k_base+leb128    | +0.0803 (+2.2%)  | +0.1063 (+2.9%)  | +0.1162 (+3.2%)  | +0.1150 (+3.1%)  | +0.0347 (+0.9pp) | WIDENS  |
| lzma_fast         | r50k_base+fixed_u16 | +0.2840 (+7.9%)  | +0.3083 (+8.5%)  | +0.3153 (+8.6%)  | +0.3177 (+8.7%)  | +0.0337 (+0.8pp) | WIDENS  |
| lzma_fast         | r50k_base+leb128    | +0.0723 (+2.0%)  | +0.0935 (+2.6%)  | +0.0993 (+2.7%)  | +0.1011 (+2.8%)  | +0.0287 (+0.8pp) | WIDENS  |
| lzma_tuned_lp1pb1 | p50k_base+fixed_u16 | +0.2986 (+8.2%)  | +0.3372 (+9.1%)  | +0.3523 (+9.4%)  | +0.3564 (+9.6%)  | +0.0578 (+1.4pp) | WIDENS  |
| lzma_tuned_lp1pb1 | r50k_base+fixed_u16 | +0.2896 (+8.0%)  | +0.3227 (+8.7%)  | +0.3330 (+8.9%)  | +0.3413 (+9.2%)  | +0.0517 (+1.2pp) | WIDENS  |
| zstd_12           | cl100k_base+leb128  | +0.2017 (+6.4%)  | +0.2138 (+6.8%)  | +0.2161 (+6.8%)  | +0.2158 (+6.8%)  | +0.0141 (+0.4pp) | WIDENS  |
| zstd_12           | o200k_base+leb128   | +0.1814 (+5.8%)  | +0.1928 (+6.1%)  | +0.1955 (+6.1%)  | +0.1960 (+6.2%)  | +0.0146 (+0.4pp) | WIDENS  |
| zstd_12           | p50k_base+fixed_u16 | +0.1918 (+6.1%)  | +0.2023 (+6.4%)  | +0.2081 (+6.5%)  | +0.2074 (+6.5%)  | +0.0156 (+0.4pp) | WIDENS  |
| zstd_12           | p50k_base+leb128    | +0.1565 (+5.0%)  | +0.1695 (+5.4%)  | +0.1735 (+5.5%)  | +0.1726 (+5.4%)  | +0.0162 (+0.4pp) | WIDENS  |
| zstd_12           | r50k_base+fixed_u16 | +0.1837 (+5.9%)  | +0.1976 (+6.2%)  | +0.1975 (+6.2%)  | +0.1982 (+6.2%)  | +0.0145 (+0.4pp) | WIDENS  |
| zstd_12           | r50k_base+leb128    | +0.1470 (+4.7%)  | +0.1614 (+5.1%)  | +0.1630 (+5.1%)  | +0.1631 (+5.1%)  | +0.0161 (+0.5pp) | WIDENS  |
| zstd_19           | cl100k_base+leb128  | +0.0953 (+2.7%)  | +0.1178 (+3.3%)  | +0.1245 (+3.5%)  | +0.1265 (+3.5%)  | +0.0311 (+0.8pp) | WIDENS  |
| zstd_19           | o200k_base+leb128   | +0.0734 (+2.1%)  | +0.0965 (+2.7%)  | +0.1033 (+2.9%)  | +0.1052 (+2.9%)  | +0.0318 (+0.9pp) | WIDENS  |
| zstd_19           | p50k_base+fixed_u16 | +0.1770 (+5.0%)  | +0.1931 (+5.4%)  | +0.1995 (+5.6%)  | +0.1995 (+5.6%)  | +0.0225 (+0.5pp) | WIDENS  |
| zstd_19           | p50k_base+leb128    | +0.0812 (+2.3%)  | +0.0996 (+2.8%)  | +0.1056 (+2.9%)  | +0.1062 (+3.0%)  | +0.0250 (+0.7pp) | WIDENS  |
| zstd_19           | r50k_base+fixed_u16 | +0.1649 (+4.7%)  | +0.1813 (+5.1%)  | +0.1862 (+5.2%)  | +0.1858 (+5.2%)  | +0.0209 (+0.5pp) | WIDENS  |
| zstd_19           | r50k_base+leb128    | +0.0727 (+2.1%)  | +0.0899 (+2.5%)  | +0.0948 (+2.6%)  | +0.0947 (+2.7%)  | +0.0220 (+0.6pp) | WIDENS  |
| zstd_22_long      | cl100k_base+leb128  | +0.0431 (+1.2%)  | +0.0814 (+2.2%)  | +0.1133 (+3.0%)  | +0.1271 (+3.3%)  | +0.0840 (+2.1pp) | WIDENS  |
| zstd_22_long      | o200k_base+leb128   | +0.0219 (+0.6%)  | +0.0621 (+1.7%)  | +0.0945 (+2.5%)  | +0.1086 (+2.9%)  | +0.0867 (+2.2pp) | WIDENS  |
| zstd_22_long      | p50k_base+fixed_u16 | +0.1312 (+3.6%)  | +0.1619 (+4.4%)  | +0.1855 (+4.9%)  | +0.1974 (+5.2%)  | +0.0662 (+1.5pp) | WIDENS  |
| zstd_22_long      | p50k_base+leb128    | +0.0322 (+0.9%)  | +0.0654 (+1.8%)  | +0.0906 (+2.4%)  | +0.1031 (+2.7%)  | +0.0709 (+1.8pp) | WIDENS  |
| zstd_22_long      | r50k_base+fixed_u16 | +0.1199 (+3.3%)  | +0.1499 (+4.0%)  | +0.1696 (+4.5%)  | +0.1814 (+4.8%)  | +0.0615 (+1.4pp) | WIDENS  |
| zstd_22_long      | r50k_base+leb128    | +0.0260 (+0.7%)  | +0.0573 (+1.5%)  | +0.0796 (+2.1%)  | +0.0907 (+2.4%)  | +0.0647 (+1.7pp) | WIDENS  |

**32 widen, 12 flat, 0 narrow** across 44 backend/pipeline combinations spanning 64MB to 4GB.


### Q2. Does `fixed_u16` + `lp=1,pb=1` beat `LEB128` + `lc=3,lp=0,pb=0`?

| tier  | tokenizer | leb128+lc3lp0pb0 | fixed_u16+lc3lp0pb0 | fixed_u16+lc1lp1pb1 | tuned vs leb128 | lp/pb tuning alone | verdict        |
|-------|-----------|------------------|---------------------|---------------------|-----------------|--------------------|----------------|
| 64MB  | r50k_base | 3.6856           | 3.8975              | 3.9214              | +6.40%          | +0.61%             | fixed_u16 WINS |
| 64MB  | p50k_base | 3.6915           | 3.9060              | 3.9304              | +6.47%          | +0.63%             | fixed_u16 WINS |
| 256MB | r50k_base | 3.7978           | 4.0152              | 4.0344              | +6.23%          | +0.48%             | fixed_u16 WINS |
| 256MB | p50k_base | 3.8099           | 4.0295              | 4.0488              | +6.27%          | +0.48%             | fixed_u16 WINS |
| 1GB   | r50k_base | 3.8260           | 4.0480              | 4.0661              | +6.28%          | +0.45%             | fixed_u16 WINS |
| 1GB   | p50k_base | 3.8416           | 4.0668              | 4.0855              | +6.35%          | +0.46%             | fixed_u16 WINS |
| 4GB   | r50k_base | 3.8242           | 4.0454              | 4.0634              | +6.25%          | +0.44%             | fixed_u16 WINS |
| 4GB   | p50k_base | 3.8355           | 4.0602              | 4.0785              | +6.34%          | +0.45%             | fixed_u16 WINS |

### Q3. Does `manual_pool` ever beat `library_batch`?

Tokenize time only (percentages are speedup vs `library_batch`; positive = faster).

| tier  | tokenizer  | backend      | threads | chunk | library_batch_s | manual_pool   | process_pool  |
|-------|------------|--------------|---------|-------|-----------------|---------------|---------------|
| 256MB | o200k_base | lzma_extreme | 20      | 2MB   | 2.40            | 2.51 (-4.7%)  | 2.59 (-7.9%)  |
| 256MB | o200k_base | lzma_fast    | 20      | 2MB   | 2.51            | 2.43 (+3.2%)  | 2.40 (+4.4%)  |
| 256MB | o200k_base | zstd_12      | 20      | 2MB   | 2.46            | 2.30 (+6.7%)  | 2.46 (-0.0%)  |
| 256MB | o200k_base | zstd_19      | 20      | 2MB   | 2.33            | 2.45 (-4.9%)  | 2.45 (-5.0%)  |
| 256MB | r50k_base  | lzma_extreme | 20      | 2MB   | 3.40            | 3.35 (+1.5%)  | 2.82 (+16.9%) |
| 256MB | r50k_base  | lzma_fast    | 20      | 2MB   | 3.38            | 3.48 (-2.9%)  | 2.99 (+11.5%) |
| 256MB | r50k_base  | zstd_12      | 20      | 2MB   | 3.36            | 3.55 (-5.7%)  | 2.85 (+15.2%) |
| 256MB | r50k_base  | zstd_19      | 20      | 2MB   | 3.33            | 3.46 (-3.9%)  | 3.07 (+7.9%)  |
| 64MB  | o200k_base | lzma_extreme | 20      | 2MB   | 0.71            | 0.72 (-1.7%)  | 0.79 (-11.3%) |
| 64MB  | o200k_base | lzma_fast    | 20      | 2MB   | 1.19            | 0.76 (+36.4%) | 0.80 (+33.3%) |
| 64MB  | o200k_base | zstd_12      | 20      | 2MB   | 1.24            | 0.69 (+44.5%) | 0.70 (+43.6%) |
| 64MB  | o200k_base | zstd_19      | 20      | 2MB   | 0.76            | 0.63 (+16.2%) | 0.69 (+8.6%)  |
| 64MB  | r50k_base  | lzma_extreme | 20      | 2MB   | 0.98            | 0.98 (+0.7%)  | 0.81 (+17.2%) |
| 64MB  | r50k_base  | lzma_fast    | 20      | 2MB   | 1.60            | 0.92 (+42.4%) | 0.83 (+48.2%) |
| 64MB  | r50k_base  | zstd_12      | 20      | 2MB   | 0.87            | 0.92 (-5.3%)  | 0.84 (+3.8%)  |
| 64MB  | r50k_base  | zstd_19      | 20      | 2MB   | 0.89            | 0.95 (-6.8%)  | 0.85 (+5.3%)  |

**`manual_pool` beat `library_batch` in 8/16 comparable configurations.**


### Q4. What is the real `xz -T` speedup curve, and where does the dictionary-size floor kick in?

Speedup is wall-clock relative to `-T1`; the percentage beside it is the **ratio cost** of multithreading, since each MT block restarts with a fresh dictionary and loses cross-block redundancy.

`fed to xz` is the size of the stream actually handed to the compressor -- the packed token stream, not the corpus and not the compressed output. That is the quantity that sets the block count, and it is the reason pre-tokenization has a hidden parallelism cost: shrinking the compressor's input also shrinks the number of blocks available to split across threads.

| tier  | pipeline   | backend      | fed to xz | blocks | T1_s   | T1_ratio | T4             | T20             |
|-------|------------|--------------|-----------|--------|--------|----------|----------------|-----------------|
| 1GB   | raw        | lzma_extreme | 1025MB    | 8      | 1059.9 | 3.7768   | 3.78x (-1.16%) | 7.49x (-1.16%)  |
| 1GB   | raw        | lzma_fast    | 1025MB    | 16     | 889.9  | 3.7157   | 4.10x (-1.35%) | 11.76x (-1.35%) |
| 1GB   | o200k_base | lzma_extreme | ?         | ?      | 526.1  | 3.8787   | 3.64x (-1.08%) | 3.80x (-1.08%)  |
| 1GB   | o200k_base | lzma_fast    | ?         | ?      | 451.9  | 3.8179   | 3.84x (-1.27%) | 5.86x (-1.27%)  |
| 1GB   | r50k_base  | lzma_extreme | 579MB     | 5      | 639.1  | 4.1015   | 3.61x (-1.30%) | 4.97x (-1.30%)  |
| 1GB   | r50k_base  | lzma_fast    | 579MB     | 9      | 574.2  | 4.0369   | 3.26x (-1.38%) | 7.94x (-1.38%)  |
| 256MB | raw        | lzma_extreme | 256MB     | 2      | 244.7  | 3.7359   | 2.06x (-0.65%) | 2.06x (-0.65%)  |
| 256MB | raw        | lzma_fast    | 256MB     | 4      | 202.8  | 3.6837   | 3.61x (-1.05%) | 3.61x (-1.05%)  |
| 256MB | o200k_base | lzma_extreme | ?         | ?      | 119.6  | 3.8172   | 1.09x (-0.11%) | 1.03x (-0.11%)  |
| 256MB | o200k_base | lzma_fast    | 129MB     | 2      | 116.0  | 3.7760   | 1.99x (-0.78%) | 2.22x (-0.78%)  |
| 256MB | r50k_base  | lzma_extreme | 145MB     | 1      | 138.4  | 4.0434   | 1.22x (-0.70%) | 1.22x (-0.70%)  |
| 256MB | r50k_base  | lzma_fast    | 145MB     | 2      | 127.1  | 3.9968   | 2.25x (-1.09%) | 2.43x (-1.09%)  |
| 4GB   | raw        | lzma_extreme | 4096MB    | 32     | 3835.6 | 3.7701   | 3.85x (-1.27%) | 10.82x (-1.27%) |
| 4GB   | raw        | lzma_fast    | 4096MB    | 64     | 3270.7 | 3.7064   | 3.81x (-1.36%) | 11.48x (-1.36%) |
| 4GB   | o200k_base | lzma_extreme | ?         | ?      | 2387.0 | 3.8791   | 4.62x (-1.32%) | 9.71x (-1.32%)  |
| 4GB   | o200k_base | lzma_fast    | 2058MB    | 32     | 1820.7 | 3.8123   | 4.06x (-1.39%) | 10.12x (-1.39%) |
| 4GB   | r50k_base  | lzma_extreme | 2315MB    | 18     | 2288.5 | 4.0984   | 3.96x (-1.29%) | 9.43x (-1.29%)  |
| 4GB   | r50k_base  | lzma_fast    | 2315MB    | 36     | 2085.0 | 4.0284   | 4.31x (-1.35%) | 11.28x (-1.35%) |
| 64MB  | raw        | lzma_extreme | 64MB      | 1      | 50.0   | 3.6318   | 1.01x (-0.00%) | 1.01x (-0.00%)  |
| 64MB  | raw        | lzma_fast    | 64MB      | 1      | 47.8   | 3.6123   | 0.99x (-0.02%) | 1.01x (-0.02%)  |
| 64MB  | o200k_base | lzma_extreme | ?         | ?      | 23.0   | 3.6681   | 1.08x (-0.00%) | 1.10x (-0.00%)  |
| 64MB  | o200k_base | lzma_fast    | ?         | ?      | 25.1   | 3.6687   | 1.17x (-0.00%) | 1.22x (-0.00%)  |
| 64MB  | r50k_base  | lzma_extreme | 36MB      | 1      | 26.6   | 3.8975   | 1.12x (-0.00%) | 1.13x (-0.00%)  |
| 64MB  | r50k_base  | lzma_fast    | 36MB      | 1      | 25.8   | 3.8953   | 1.08x (-0.00%) | 1.14x (-0.00%)  |

The `xz -T` block-size floor is 2x the LZMA2 dictionary -- 128MiB for the 64MiB-dict profiles, 64MiB for the 32MiB `lzma_fast` profile. `--block-size` is passed only when threads > 1, so the `-T1` rows are a clean single-block baseline with a full dictionary. Below the floor xz cannot produce more than one block, so `-T` cannot help regardless of the flag -- and correspondingly costs no ratio.


## Plots

![ratio vs corpus size](ratio_vs_corpus_size.png)


![ratio gap](ratio_gap_vs_corpus_size.png)

