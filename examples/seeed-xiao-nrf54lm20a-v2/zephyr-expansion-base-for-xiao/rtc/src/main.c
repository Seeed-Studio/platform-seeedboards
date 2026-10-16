#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/rtc.h>
#include <stdio.h>
#include <time.h> // For struct tm

// Define RTC device alias from device tree
#define RTC_DEVICE_NODE DT_ALIAS(rtc)

static const struct device *rtc_dev;

/**
 * @brief Sets the RTC date and time.
 *
 * @param dev Pointer to the RTC device structure.
 * @param year Year (e.g., 2025)
 * @param month Month (1-12)
 * @param day Day (1-31)
 * @param hour Hour (0-23)
 * @param minute Minute (0-59)
 * @param second Second (0-59)
 * @return 0 on success, or a negative errno code on failure.
 */
int set_rtc_time(const struct device *dev, int year, int month, int day,
                 int hour, int minute, int second)
{
    struct rtc_time new_time;
    struct tm temp_tm = {0}; // Temporary struct tm for conversion

    // Populate temporary tm structure
    temp_tm.tm_year = year - 1900; // tm_year is years since 1900
    temp_tm.tm_mon = month - 1;   // tm_mon is months since January (0-11)
    temp_tm.tm_mday = day;
    temp_tm.tm_hour = hour;
    temp_tm.tm_min = minute;
    temp_tm.tm_sec = second;

    // Convert to struct rtc_time
    new_time.tm_year = temp_tm.tm_year;
    new_time.tm_mon = temp_tm.tm_mon;
    new_time.tm_mday = temp_tm.tm_mday;
    new_time.tm_hour = temp_tm.tm_hour;
    new_time.tm_min = temp_tm.tm_min;
    new_time.tm_sec = temp_tm.tm_sec;
    new_time.tm_wday = 0; // Not critical for PCF8563
    new_time.tm_yday = 0;
    new_time.tm_isdst = 0;

    int ret = rtc_set_time(dev, &new_time);
    if (ret == 0) {
        printk("RTC time set to: %04d-%02d-%02d %02d:%02d:%02d\n",
               year, month, day, hour, minute, second);
    } else {
        printk("Error: Failed to set RTC time! Code: %d\n", ret);
    }
    return ret;
}

int main(void)
{
    int ret;
    struct rtc_time rtc_current_time;

    printk("--- NCS RTC PCF8563 Example ---\n");

    // Get RTC device instance
    rtc_dev = DEVICE_DT_GET(RTC_DEVICE_NODE);
    if (!device_is_ready(rtc_dev)) {
        printk("Error: RTC device not ready!\n");
        return 0;
    }
    printk("RTC device ready.\n");

    // Set initial RTC date and time using the helper function
    printk("\nSetting initial RTC time...\n");
    ret = set_rtc_time(rtc_dev, 2025, 7, 23, 11, 30, 0); // 2025-07-23 11:30:00
    if (ret != 0) {
        return 0; // Exit if time setting failed
    }

    // Continuously read and print RTC time
    printk("\nContinuously reading RTC time...\n");
    while (1) {
        ret = rtc_get_time(rtc_dev, &rtc_current_time);
        if (ret == 0) {
            printk("Current RTC Time: %04d-%02d-%02d %02d:%02d:%02d\n",
                   rtc_current_time.tm_year + 1900, rtc_current_time.tm_mon + 1, rtc_current_time.tm_mday,
                   rtc_current_time.tm_hour, rtc_current_time.tm_min, rtc_current_time.tm_sec);
        } else {
            printk("Error: Failed to get RTC time! Code: %d\n", ret);
        }
        k_sleep(K_SECONDS(1)); // Read every second
    }

    return 0;
}
