#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(battery, CONFIG_LOG_DEFAULT_LEVEL);

#if !DT_NODE_EXISTS(DT_PATH(zephyr_user)) || \
	!DT_NODE_HAS_PROP(DT_PATH(zephyr_user), io_channels)
#error "No suitable devicetree overlay specified"
#endif

#define DT_SPEC_AND_COMMA(node_id, prop, idx) \
	ADC_DT_SPEC_GET_BY_IDX(node_id, idx),

/* Data of ADC io-channels specified in devicetree. */
static const struct adc_dt_spec adc_channels[] = {
	DT_FOREACH_PROP_ELEM(DT_PATH(zephyr_user), io_channels,
						 DT_SPEC_AND_COMMA)};

static const struct device *const vbat_reg = DEVICE_DT_GET(DT_NODELABEL(vbat_pwr));

int main(void)
{
	int err;
	uint16_t buf;
	int32_t val_mv;
	struct adc_sequence sequence = {
		.buffer = &buf,
		/* buffer size in bytes, not number of samples */
		.buffer_size = sizeof(buf),
	};

	regulator_enable(vbat_reg);
	k_sleep(K_MSEC(100));

	/* Configure channels individually prior to sampling. */
	if (!adc_is_ready_dt(&adc_channels[7]))
	{
		printf("ADC controller device %s not ready\n", adc_channels[7].dev->name);
		return 0;
	}

	err = adc_channel_setup_dt(&adc_channels[7]);
	if (err < 0)
	{
		printf("Could not setup channel #7 (%d)\n", err);
		return 0;
	}

	(void)adc_sequence_init_dt(&adc_channels[7], &sequence);

	err = adc_read_dt(&adc_channels[7], &sequence);
	if (err < 0)
	{
		printf("Could not read (%d)\n", err);
		return 0;
	}

	/*
	 * If using differential mode, the 16 bit value
	 * in the ADC sample buffer should be a signed 2's
	 * complement value.
	 */
	if (adc_channels[7].channel_cfg.differential)
	{
		val_mv = (int32_t)((int16_t)buf);
	}
	else
	{
		val_mv = (int32_t)buf;
	}
	err = adc_raw_to_millivolts_dt(&adc_channels[7],
								   &val_mv);
	/* conversion to mV may not be supported, skip if not */
	if (err < 0)
	{
		printf(" value in mV not available\n");
	}
	else
	{
		printf("bat vol = %" PRId32 " mV\n", val_mv * 2);
	}

	regulator_disable(vbat_reg);
	return 0;
}

