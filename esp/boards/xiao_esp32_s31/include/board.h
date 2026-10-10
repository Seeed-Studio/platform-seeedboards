/* Board facts for the Seeed Studio XIAO ESP32-S31 Sense.
 *
 * Single source of truth for board-level pins and constants, extracted
 * from the V03 schematic (2026-10-10) and the ESP32-S31NRV32 datasheet
 * v0.5. Include this header instead of copying #defines into every
 * sample; the component is attached automatically through the board
 * manifest key build.esp-idf.extra_component_dirs.
 *
 * Edge pads (SMD castellated edge, U11 on the schematic):
 *   D0/A0   = ADC0 (dedicated analog pin, chip pin 55)
 *   D1..D3  = GPIO43 / GPIO44 / GPIO45          (A1..A3)
 *   D4/D5   = GPIO7 / GPIO6                     (LP I2C SDA/SCL)
 *   D6      = GPIO58                            (UART0 TX)
 *   D13..D17= GPIO12 / GPIO13 / GPIO15 / GPIO18 / GPIO19
 *   D18/D19 = GPIO4 / GPIO5                     (CAN FD TX/RX)
 *   D20     = GPIO20
 *   D21..D23= GPIO50 / GPIO51 / GPIO52          (A8..A10)
 *   pads 8..11  = GPIO59 / GPIO46 / GPIO47 / GPIO48
 *   pads 12..14 = 3V3 / GND / VBUS
 *   pads 15/16  = GPIO8 / GPIO9
 *   pads 28..31 = GPIO53 / GPIO38 / GPIO39 / GPIO40
 *
 * USB: the USB-C connector goes to the dedicated OTG HS pins (chip pins
 * 44/45). USB-Serial/JTAG as an alternate reaches GPIO33/34 on the B2B
 * connector (P22/P23); pin JTAG (MTMS/MTCK/MTDO/MTDI) is on B2B P2..P5.
 *
 * Flash (32 MB quad SPI) and PSRAM (32 MB octal, in package) sit on the
 * fixed SPI bus — not available as GPIOs.
 */

#pragma once

#include "soc/gpio_num.h"

#ifdef __cplusplus
extern "C" {
#endif

/* On-board yellow user LED, lights while the GPIO is driven LOW
 * (3V3 -> series resistor -> LED -> GPIO23; schematic refdes D3). */
#define BOARD_LED_GPIO GPIO_NUM_23
#define BOARD_LED_ACTIVE_LOW 1

/* BOOT button pulls GPIO61 to GND; with GPIO60 high (its required idle)
 * that selects Joint Download Boot, releasing it selects SPI boot. */
#define BOARD_BTN_BOOT_GPIO GPIO_NUM_61

/* Battery sense: resistor divider into GPIO49, gated by a high-side
 * switch on GPIO25 — drive the enable high before sampling, low after. */
#define BOARD_VBAT_ADC_GPIO GPIO_NUM_49
#define BOARD_VBAT_EN_GPIO GPIO_NUM_25

/* Low-power I2C bus wired to the D4/D5 pads. */
#define BOARD_I2C_SDA_GPIO GPIO_NUM_7
#define BOARD_I2C_SCL_GPIO GPIO_NUM_6

/* CAN FD bus wired to the D18/D19 pads. */
#define BOARD_CAN_TX_GPIO GPIO_NUM_4
#define BOARD_CAN_RX_GPIO GPIO_NUM_5

/* UART0 console: TX is the D6 pad (GPIO58). GPIO59 (adjacent pad 8) is
 * the expected RX — verify against the datasheet UART0 defaults before
 * relying on it. */
#define BOARD_UART0_TX_GPIO GPIO_NUM_58
#define BOARD_UART0_RX_GPIO GPIO_NUM_59 /* verify before use */

/* Crystal. */
#define BOARD_XTAL_MHZ 40

#ifdef __cplusplus
}
#endif
