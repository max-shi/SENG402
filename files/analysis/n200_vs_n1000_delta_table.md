# n=200 confirmatory vs n=1000 extended: Cliff's delta by dimension

Sorted by |delta| at n=200, descending. `pass?` = passes Layer 1 (Holm p<0.05 AND |delta|>=0.33). Only `emo_anger` ever passes, and only at n=200, it fails at n=1000 despite an extremely small p-value, because its effect size drops below the practical-significance threshold once measured more precisely.

| dimension | n=200 δ | n=200 pass? | n=200 Holm p | n=1000 δ | n=1000 pass? | n=1000 Holm p |
|---|---:|:---:|---:|---:|:---:|---:|
| emo_anger | -0.343 | YES | 2.32e-08 | -0.296 | no | 8.76e-31 |
| conflict | -0.297 | no | 3.09e-06 | -0.271 | no | 3.60e-25 |
| achieve | +0.230 | no | 8.93e-04 | +0.072 | no | 4.05e-02 |
| WPS | +0.192 | no | 9.88e-03 | +0.182 | no | 2.23e-11 |
| emo_sad | +0.189 | no | 9.88e-03 | +0.180 | no | 1.91e-11 |
| tentat | -0.152 | no | 8.37e-02 | -0.182 | no | 2.00e-11 |
| BigWords | +0.149 | no | 8.94e-02 | +0.150 | no | 6.94e-08 |
| ipron | -0.109 | no | 4.72e-01 | -0.066 | no | 7.41e-02 |
| curiosity | +0.105 | no | 4.88e-01 | +0.065 | no | 7.41e-02 |
| certitude | +0.059 | no | 1.00e+00 | +0.033 | no | 7.60e-01 |
| emo_neg | -0.047 | no | 1.00e+00 | -0.034 | no | 7.60e-01 |
| emotion | -0.038 | no | 1.00e+00 | -0.031 | no | 7.60e-01 |
| Tone | +0.030 | no | 1.00e+00 | +0.005 | no | 8.52e-01 |
| motion | -0.028 | no | 1.00e+00 | -0.131 | no | 3.68e-06 |
| risk | -0.027 | no | 1.00e+00 | -0.040 | no | 5.82e-01 |
