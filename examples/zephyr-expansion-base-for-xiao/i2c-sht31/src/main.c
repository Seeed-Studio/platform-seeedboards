#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <stdio.h>
#include <stdlib.h>

// Define SHT31 device node from device tree
#define SHT31_NODE DT_ALIAS(sht31)

int main(void)
{
    const struct device *sht31_dev;
    struct sensor_value temp_val, hum_val;
    int ret;

    printk("--- NCS SHT31 Sensor Example ---\n");

    // Get SHT31 device instance
    sht31_dev = DEVICE_DT_GET(SHT31_NODE);
    if (!device_is_ready(sht31_dev)) {
        printk("Error: SHT31 device not ready!\n");
        return 0;
    }
    printk("SHT31 device ready.\n");

    while (1) {
        // Trigger a new measurement from the SHT31
        ret = sensor_sample_fetch(sht31_dev);
        if (ret != 0) {
            printk("Error: Failed to fetch SHT31 sample! Code: %d\n", ret);
            k_sleep(K_SECONDS(2)); // Wait before retrying
            continue;
        }

        // Get temperature value
        ret = sensor_channel_get(sht31_dev, SENSOR_CHAN_AMBIENT_TEMP, &temp_val);
        if (ret != 0) {
            printk("Error: Failed to get temperature value! Code: %d\n", ret);
            k_sleep(K_SECONDS(2));
            continue;
        }

        // Get humidity value
        ret = sensor_channel_get(sht31_dev, SENSOR_CHAN_HUMIDITY, &hum_val);
        if (ret != 0) {
            printk("Error: Failed to get humidity value! Code: %d\n", ret);
            k_sleep(K_SECONDS(2));
            continue;
        }

        // Avoid floating-point formatting on small stacks.
        printk("Temperature: %d.%06d C | Humidity: %d.%06d %%\n",
               temp_val.val1, abs(temp_val.val2),
               hum_val.val1, abs(hum_val.val2));

        k_sleep(K_SECONDS(2)); // Read every 2 seconds
    }

    return 0;
}
