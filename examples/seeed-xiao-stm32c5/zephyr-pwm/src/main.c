/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 PWM duty-cycle test.
 */

#include <zephyr/device.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#define PWM_D0_NODE DT_NODELABEL(pwm_d0)
#define PWM_D1_NODE DT_NODELABEL(pwm_d1)
#define PWM_D2_NODE DT_NODELABEL(pwm_d2)

#define PWM_PERIOD_NS PWM_MSEC(1)
#define STATUS_INTERVAL_MS 1000

struct pwm_output {
	const char *name;
	const struct pwm_dt_spec spec;
	uint32_t duty_percent;
};

static const struct pwm_output outputs[] = {
	{
		.name = "D0 / PA0 / TIM2_CH1",
		.spec = PWM_DT_SPEC_GET(PWM_D0_NODE),
		.duty_percent = 25U,
	},
	{
		.name = "D1 / PA1 / TIM2_CH2",
		.spec = PWM_DT_SPEC_GET(PWM_D1_NODE),
		.duty_percent = 50U,
	},
	{
		.name = "D2 / PA2 / TIM2_CH3",
		.spec = PWM_DT_SPEC_GET(PWM_D2_NODE),
		.duty_percent = 75U,
	},
};

static int set_pwm_output(const struct pwm_output *output)
{
	uint32_t pulse_ns = (output->spec.period * output->duty_percent) / 100U;

	return pwm_set_dt(&output->spec, output->spec.period, pulse_ns);
}

int main(void)
{
	printk("XIAO STM32C5 PWM duty-cycle test\n");
	printk("PWM frequency: 1 kHz, period: %u ns\n", PWM_PERIOD_NS);
	printk("Expected waveform: D0=25%%, D1=50%%, D2=75%% duty cycle\n");

	for (size_t i = 0; i < ARRAY_SIZE(outputs); i++) {
		const struct pwm_output *output = &outputs[i];
		int ret;

		if (!pwm_is_ready_dt(&output->spec)) {
			printk("%s PWM device is not ready\n", output->name);
			return 0;
		}

		ret = set_pwm_output(output);
		if (ret < 0) {
			printk("Failed to set %s to %u%% duty: %d\n",
			       output->name, output->duty_percent, ret);
			return 0;
		}

		printk("%s set to %u%% duty\n", output->name, output->duty_percent);
	}

	while (true) {
		printk("PWM running: D0=25%%, D1=50%%, D2=75%% at 1 kHz\n");
		k_msleep(STATUS_INTERVAL_MS);
	}
}
