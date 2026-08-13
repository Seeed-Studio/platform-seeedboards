# Offline image sources

The test images are Wikimedia Commons files released under CC0.  They were
downloaded on 2026-07-23, resized to 128 x 128 pixels with center crop, then
encoded as big-endian RGB565 into `src/offline_images.c`.  The input byte order
matches the official `person_detection` application's `extract_pixel()`.

| Embedded name | Purpose | Source | Creator | License |
| --- | --- | --- | --- | --- |
| `person_cc0` | Positive: contains a walking person | [Man walking through the Saint Roch neighborhood, Quebec City](https://upload.wikimedia.org/wikipedia/commons/b/bc/Man_walking_through_the_Saint_Roch_neighborhood%2C_Quebec_City%2C_Province_of_Quebec%2C_Canada.jpg) | Wilfredor | [CC0](https://creativecommons.org/publicdomain/zero/1.0/) |
| `penguin_cc0` | Negative: no person | [Full-body portrait of an African penguin](https://upload.wikimedia.org/wikipedia/commons/0/0f/Full-body_portrait_of_an_African_penguin.jpg) | Stanislav Stelmakhovich | [CC0](https://creativecommons.org/publicdomain/zero/1.0/) |
