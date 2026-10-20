#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  Serial.println("platform-unified samd uart demo");
}

void loop() {
  if (Serial.available()) {
    Serial.write(Serial.read());
  }
}
