/*
 * Blink
 * Turns on an LED on for one second,
 * then off for one second, repeatedly.
 */

#include <Arduino.h>

// Some board variants do not define LED_BUILTIN. Provide a fallback so the
// example always compiles.
#ifndef LED_BUILTIN
#if defined(PIN_LED)
#define LED_BUILTIN PIN_LED
#elif defined(PICO_DEFAULT_LED_PIN)
#define LED_BUILTIN PICO_DEFAULT_LED_PIN
#elif defined(ARDUINO_ARCH_ESP32)
// Common default for many ESP32 variants; users can adjust if needed.
#define LED_BUILTIN 2
#else
// Reasonable default for many Arduino-compatible boards.
#define LED_BUILTIN D0
#endif
#endif

void setup()
{
  // initialize LED digital pin as an output.
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop()
{
  // turn the LED on (HIGH is the voltage level)
  digitalWrite(LED_BUILTIN, HIGH);
  // wait for a second
  delay(1000);
  // turn the LED off by making the voltage LOW
  digitalWrite(LED_BUILTIN, LOW);
   // wait for a second
  delay(1000);
}
