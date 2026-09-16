# Model record card

| Field | Wake word model (WW) | Keyword model (KWS) |
|---|---|---|
| Model name / version | Hello Seeed / solution 95647 | seeed key word / solution 95649 |
| Edge AI Lab project / export date | `Hello_Seeed_95647_wake_word.zip` / 2026-08-25 | `seeed_key word_95649_kws.zip` / 2026-08-25 |
| Target | nRF54LM20B Axon NPU | nRF54LM20B Axon NPU |
| Input spec | 16 kHz, mono, 16-bit; 160 samples (10 ms) | 16 kHz, mono, 16-bit; 160 samples (10 ms) |
| Labels & output indices | 0: `hello seeed` | 0: `OTHER`; 1: `SILENCE`; 2: `no`; 3: `ok`; 4: `opus`; 5: `stop`; 6: `yes` |
| Train/validation/test split | TBD | TBD |
| Axon interlayer buffer | 6048 bytes | 6656 bytes |
| Axon psum buffer | 0 bytes | 0 bytes |
| On-device thresholds | TBD | TBD |
| On-site test results | TBD | TBD |
