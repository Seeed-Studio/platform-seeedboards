#include <Arduino.h>
void setup() { Serial.begin(115200); Serial.println("platform-seeed esp32 uart"); }
void loop() { if (Serial.available()) Serial.write(Serial.read()); }
