#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/sys/util.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/uart.h>
#ifdef CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP
#include <zephyr/drivers/regulator.h>
#endif

LOG_MODULE_REGISTER(mic_capture_sample, LOG_LEVEL_INF);

#define RECORD_TIME_S  10                // Recording duration (seconds)
#define SAMPLE_RATE_HZ 16000            // Sample rate (Hz)
#define SAMPLE_BIT_WIDTH 16             // Sample bit width (bits)
#define BYTES_PER_SAMPLE (SAMPLE_BIT_WIDTH / 8) // Bytes per sample

#define READ_TIMEOUT_MS 1000            // DMIC read timeout (ms)
#define CHUNK_DURATION_MS 100           // Duration of each chunk (ms)
#define CHUNK_SIZE_BYTES  (BYTES_PER_SAMPLE * (SAMPLE_RATE_HZ * CHUNK_DURATION_MS) / 1000) // Chunk size (bytes)
#define CHUNK_COUNT       8             // Number of blocks in memory pool
#define TOTAL_CHUNKS      (RECORD_TIME_S * 1000 / CHUNK_DURATION_MS) // Total number of chunks

static const struct device *const dmic_dev = DEVICE_DT_GET(DT_ALIAS(dmic20)); // DMIC device handle
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios); // LED device descriptor
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios); // Button device descriptor
static const struct device *const console_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_console)); // Console UART device

#ifdef CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP
static const struct device *const power_en_dev = DEVICE_DT_GET(DT_NODELABEL(power_en));
static const struct device *const dmic_vdd_dev = DEVICE_DT_GET(DT_NODELABEL(dmic_vdd));

static int enable_dmic_power(void)
{
    int ret;

    if (!device_is_ready(power_en_dev)) {
        LOG_ERR("power_en regulator is not ready");
        return -ENODEV;
    }

    if (!device_is_ready(dmic_vdd_dev)) {
        LOG_ERR("dmic_vdd regulator is not ready");
        return -ENODEV;
    }

    ret = regulator_enable(power_en_dev);
    if (ret < 0 && ret != -EALREADY) {
        LOG_ERR("Failed to enable power_en: %d", ret);
        return ret;
    }

    ret = regulator_enable(dmic_vdd_dev);
    if (ret < 0 && ret != -EALREADY) {
        LOG_ERR("Failed to enable dmic_vdd: %d", ret);
        return ret;
    }

    k_sleep(K_MSEC(20));

    return 0;
}
#endif

K_MEM_SLAB_DEFINE_STATIC(mem_slab, CHUNK_SIZE_BYTES, CHUNK_COUNT, 4); // Audio data memory pool
K_MSGQ_DEFINE(audio_msgq, sizeof(void *), CHUNK_COUNT, 4);

static K_SEM_DEFINE(tx_done_sem, 0, 1); // Button semaphore
static K_SEM_DEFINE(button_sem, 0, 1); // UART TX done semaphore

static const uint8_t packet_start[] = {0xAA, 0x55, 'S', 'T', 'A', 'R', 'T'}; // Packet start marker
static const uint8_t packet_end[] = {0xAA, 0x55, 'E', 'N', 'D'};             // Packet end marker

static struct gpio_callback button_cb_data;

/**
 * @brief UART callback function
 *
 * @param dev UART device pointer
 * @param evt UART event
 * @param user_data User data (unused)
 */
static void uart_tx_callback(const struct device *dev, struct uart_event *evt, void *user_data)
{
    if (evt->type == UART_TX_DONE) {
        k_sem_give(&tx_done_sem);
    }
}

/**
 * @brief Button interrupt callback function
 *
 * @param dev Button device pointer
 * @param cb  Callback structure pointer
 * @param pins Triggered pins
 */
void button_pressed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    k_sem_give(&button_sem);
}

/**
 * @brief Send a data packet via UART (polling, for small packets)
 *
 * @param data Data pointer
 * @param len  Data length
 */
static void send_packet_poll(const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        uart_poll_out(console_dev, data[i]);
    }
}

/**
 * @brief UART writer thread function
 *
 * This thread continuously reads audio data from the message queue and sends it via UART.
 * It waits for the semaphore to signal that the previous transmission is done before sending the next chunk.
 */
void uart_writer_thread(void *p1, void *p2, void *p3)
{
    uart_callback_set(console_dev, uart_tx_callback, NULL);

    while (true) {
        void *buffer;
        k_msgq_get(&audio_msgq, &buffer, K_FOREVER);

        if (buffer == NULL) {
            send_packet_poll(packet_end, sizeof(packet_end));
            continue;
        }
        
        uart_tx(console_dev, buffer, CHUNK_SIZE_BYTES, SYS_FOREVER_US);
        k_sem_take(&tx_done_sem, K_FOREVER);
        
        k_mem_slab_free(&mem_slab, buffer);
    }
}


K_THREAD_DEFINE(uart_writer_tid, 2048, uart_writer_thread, NULL, NULL, NULL,
                K_PRIO_COOP(7), 0, 0);

static struct pcm_stream_cfg stream_cfg = {
    .pcm_rate = SAMPLE_RATE_HZ,
    .pcm_width = SAMPLE_BIT_WIDTH,
    .block_size = CHUNK_SIZE_BYTES,
    .mem_slab = &mem_slab,
}; // PCM stream configuration

static struct dmic_cfg dmic_config = {
    .io = {
        .min_pdm_clk_freq = 1000000,
        .max_pdm_clk_freq = 3500000,
        .min_pdm_clk_dc = 40,
        .max_pdm_clk_dc = 60,
    },
    .streams = &stream_cfg,
    .channel = {
        .req_num_streams = 1,
        .req_num_chan = 1,
    },
}; // DMIC configuration

/**
 * @brief Record audio from DMIC and stream it via UART
 *
 * @return 0 on success, negative error code on failure
 */
static int record_and_stream_audio(void)
{
    int ret;
    void *buffer;
    uint32_t size;

    k_msgq_purge(&audio_msgq);

    ret = dmic_configure(dmic_dev, &dmic_config);
    if (ret < 0) {
        LOG_ERR("Failed to configure DMIC: %d", ret);
        return ret;
    }

    ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
    if (ret < 0) {
        LOG_ERR("Failed to start DMIC: %d", ret);
        return ret;
    }

    ret = dmic_read(dmic_dev, 0, &buffer, &size, READ_TIMEOUT_MS);
    if (ret < 0) {
        LOG_WRN("Failed to read discard chunk: %d", ret);
    } else {
        k_mem_slab_free(&mem_slab, buffer);
    }

    send_packet_poll(packet_start, sizeof(packet_start));

    for (int i = 0; i < TOTAL_CHUNKS; i++) {
        ret = dmic_read(dmic_dev, 0, &buffer, &size, READ_TIMEOUT_MS);
        if (ret < 0) {
            LOG_ERR("Failed to read from DMIC: %d", ret);
            break;
        }

        ret = k_msgq_put(&audio_msgq, &buffer, K_MSEC(500));
        if (ret != 0) {
            LOG_ERR("Failed to queue buffer. UART thread might be too slow.");
            k_mem_slab_free(&mem_slab, buffer);
            break;
        }
    }

    (void)dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);

    void *end_marker = NULL;
    k_msgq_put(&audio_msgq, &end_marker, K_NO_WAIT);

    LOG_INF("Audio capture finished and data queued.");
    return 0;
}

/**
 * @brief Main function, initializes peripherals and waits for button to trigger recording in a loop
 *
 * @return Always returns 0
 */
int main(void)
{
    int ret;

	// Check if all required devices are ready
    if (!device_is_ready(dmic_dev) || !device_is_ready(led.port) ||
        !device_is_ready(button.port) || !device_is_ready(console_dev)) {
        LOG_ERR("A required device is not ready.");
        return -ENODEV;
    }

#ifdef CONFIG_BOARD_XIAO_NRF54LM20A_NRF54LM20A_CPUAPP
    ret = enable_dmic_power();
    if (ret < 0) {
        return ret;
    }
#endif

	// Configure DMIC channel mapping
    dmic_config.channel.req_chan_map_lo = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT);

    // Configure LED as output
    ret = gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
    if (ret < 0) { return ret; }

    // Configure button as input and enable interrupt
    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret < 0) { return ret; }
    ret = gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_TO_ACTIVE);
    if (ret < 0) { return ret; }
    gpio_init_callback(&button_cb_data, button_pressed, BIT(button.pin));
    gpio_add_callback(button.port, &button_cb_data);

    LOG_INF("Zephyr Audio Streamer Ready.");
    LOG_INF("Press button SW0 to start recording...");

    // Main loop, wait for button to trigger recording
    while (1) {
        k_sem_take(&button_sem, K_FOREVER);
        LOG_INF("Button pressed, starting capture...");

        gpio_pin_set_dt(&led, 0);
        record_and_stream_audio();
        gpio_pin_set_dt(&led, 1);

        LOG_INF("\nPress button SW0 to start recording again...");
    }

    return 0;
}