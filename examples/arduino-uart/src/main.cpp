// Portable UART echo demo. On cores where Serial is a USB CDC class
// (Adafruit TinyUSB), the library must be included for it to link.
#if defined(USE_TINYUSB)
#include <Adafruit_TinyUSB.h>
#endif

#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  Serial.println("platform-seeed uart echo");
}

void loop() {
  if (Serial.available()) {
    Serial.write(Serial.read());
  }
}
