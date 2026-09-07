/* 2026-09-07T06:17:56.022052 */
/*
* Copyright (c) 2026 Nordic Semiconductor ASA
* SPDX-License-Identifier: Apache-2.0
*/
#include "nrf_edgeai_user_model.h"
#include "nrf_edgeai_user_types.h"
#include <nrf_edgeai/nrf_edgeai_platform.h>
#include <nrf_edgeai/rt/private/nrf_edgeai_interfaces.h>
#include <assert.h>

//////////////////////////////////////////////////////////////////////////////
/* Nordic EdgeAI Lab Solution ID and Runtime Version */
#define EDGEAI_LAB_SOLUTION_ID_STR      "95957"
#define EDGEAI_RUNTIME_VERSION_COMBINED 0x00000202

//////////////////////////////////////////////////////////////////////////////
#define INPUT_TYPE                         f32

/** User input features type */
#define INPUT_FEATURE_DATA_TYPE            NRF_EDGEAI_INPUT_F32

/** Number of unique features in the original input sample */
#define INPUT_UNIQ_FEATURES_NUM            6

/** Number of unique features actually used by NN from the original input sample */
#define INPUT_UNIQ_FEATURES_USED_NUM       6

/** Number of input feature samples that should be collected in the input window
 *  feature_sample = 1 * INPUT_UNIQ_FEATURES_NUM
 */
#define INPUT_WINDOW_SIZE                  100

/** Number of input feature samples on that the input window is shifted */
#define INPUT_WINDOW_SHIFT                 33

/** Number of subwindows in input feature window,
* the SUBWINDOW_SIZE = INPUT_WINDOW_SIZE / INPUT_SUBWINDOW_NUM
* if the window size is not divisible by the number of subwindows without a remainder,
* the remainder is added to the last subwindow size */
#define INPUT_SUBWINDOW_NUM                 0

#define INPUT_UNIQUE_SCALES_NUM (sizeof(INPUT_FEATURES_SCALE_MIN) / sizeof(INPUT_FEATURES_SCALE_MIN[0])) 

/** Defines input(also used for LAG) features MIN scaling factor
 */
static const nrf_user_input_t INPUT_FEATURES_SCALE_MIN[] = {
 -15434902.0000000, -30507292.0000000, -16913666.0000000, -3578447.0000000,
 -5623623.0000000, -5426925.0000000 };

/** Defines input(also used for LAG) features MAX scaling factor
 */
static const nrf_user_input_t INPUT_FEATURES_SCALE_MAX[] = {
 18345770.0000000, 10704291.0000000, 36697524.0000000, 3255300.0000000,
 5759847.0000000, 7628483.0000000 };

/** Defines which unique features from the input data will be used/collected,
 *  one bit for one unique feature, starting from LSB
 */
#define INPUT_FEATURES_USAGE_MASK NULL

/** Defines which unique input features is used for LAG features processing,
 *  one bit for one unique feature, starting from LSB
 */
#define INPUT_FEATURES_USED_FOR_LAGS_MASK NULL

//////////////////////////////////////////////////////////////////////////////
#define MODEL_TYPE                 __NRF_EDGEAI_MODEL_AXON
#define MODEL_TASK                 1
#define MODEL_OUTPUTS_NUM          2

#define MODEL_USES_AS_INPUT_INPUT_FEATURES 0
#define MODEL_USES_AS_INPUT_DSP_FEATURES 1
#define MODEL_USES_AS_INPUT_MASK ((MODEL_USES_AS_INPUT_INPUT_FEATURES << 0) | (MODEL_USES_AS_INPUT_DSP_FEATURES << 1)) 

#if MODEL_TYPE == __NRF_EDGEAI_MODEL_AXON 
#include <drivers/axon/nrf_axon_nn_infer.h>  
#include <axon/nrf_axon_platform.h> 
#include "nrf_edgeai_user_model_axon.h" 
#define P_MODEL_INSTANCE &model_axon_user_instance_95957
#else  // MODEL_TYPE == __NRF_EDGEAI_MODEL_NEUTON
#define P_MODEL_INSTANCE &model_neuton_user_instance_ 
#endif


#define NN_DECODED_OUTPUT_INIT                 \
.classif = {                                   \
   .predicted_class = 0,                       \
   .num_classes = MODEL_OUTPUTS_NUM,           \
}

//////////////////////////////////////////////////////////////////////////////
/** Input feature buffer element size, 
 * if quantization of model is bigger than input features size in bits, 
 * the size of input buffer should aligned to nrf_user_neuron_t */ 
#define INPUT_TYPE_SIZE \
    ((sizeof(nrf_user_input_t) > sizeof(nrf_user_neuron_t)) ? sizeof(nrf_user_input_t) : sizeof(nrf_user_neuron_t)) 

/** Input features window size in bytes to allocate statically */ 
#define INPUT_WINDOW_BUFFER_SIZE_BYTES \
    (INPUT_WINDOW_SIZE * INPUT_UNIQ_FEATURES_NUM * INPUT_TYPE_SIZE) 

static uint8_t input_window_[INPUT_WINDOW_BUFFER_SIZE_BYTES] __NRF_EDGEAI_ALIGNED; 

#define INPUT_WINDOW_MEMORY    &input_window_[0] 

static nrf_edgeai_window_ctx_t input_window_ctx_; 
#define P_INPUT_WINDOW_CTX     &input_window_ctx_ 

//////////////////////////////////////////////////////////////////////////////
/** The maximum number of extracted features that user used for all unique input features */
#define EXTRACTED_FEATURES_NUM  66

#define EXTRACTED_FEATURES_META_TYPE f32 

/** DSP feature buffer element size,
 * if quantization of model is bigger than DSP features size in bits,
 * the size of extracted DSP features buffer should aligned to nrf_user_neuron_t */
#define EXTRACTED_FEATURE_SIZE_BYTES                                                  \
    ((sizeof(nrf_user_feature_t) > sizeof(nrf_user_neuron_t)) ? sizeof(nrf_user_feature_t) : \
                                                            sizeof(nrf_user_neuron_t))

/** Size of extracted features buffer in bytes */
#define EXTRACTED_FEATURES_BUFFER_SIZE_BYTES (EXTRACTED_FEATURES_NUM * EXTRACTED_FEATURE_SIZE_BYTES) 

/** Defines feature extraction masks used as nrf_edgeai_features_mask_t,
 *  64 bit for one unique input feature, @ref nrf_edgeai_features_mask_t to see bitmask
 */

static const uint64_t FEATURES_EXTRACTION_MASK[] = {
 0xc79f00000000, 0xc79f00000000, 0xc79f00000000, 0xc79f00000000,
 0xc79f00000000, 0xc79f00000000 };

/** Defines arguments used while feature extraction
 */

/** Defines arguments used while feature extraction
 */
#define FEATURES_EXTRACTION_ARGUMENTS NULL

/** Defines extracted features MIN scaling factor
 */
static const nrf_user_feature_t EXTRACTED_FEATURES_SCALE_MIN[] = {
 -15434902.0000000, -2389233.0000000, 89731.0000000, -4928555.0000000,
 14745.5000000, 18681.2207031, 36768.7343750, 0.0303030, 0.0000000,
 30160.9804688, 19227.1308594, -30507292.0000000, -9631110.0000000,
 74178.0000000, -9703708.0000000, 13493.9697266, 17317.5292969,
 229410.4218750, 0.0202020, 0.0000000, 227126.2187500, 16858.5351562,
 -16913666.0000000, -203389.0000000, 94517.0000000, -1726959.6250000,
 16452.8398438, 20849.7519531, 218124.4843750, 0.0101010, 0.0000000,
 200374.4843750, 20206.0195312, -3578447.0000000, -65362.0000000,
 24433.0000000, -671663.8125000, 3610.2290039, 4674.0571289, 6461.7543945,
 0.0101010, 0.0000000, 5173.4799805, 3714.4243164, -5623623.0000000,
 47647.0000000, 67194.0000000, -463878.4375000, 10296.5791016,
 13990.4560547, 18809.4843750, 0.0101010, 0.0000000, 15344.4404297,
 8157.0805664, -5426925.0000000, -163711.0000000, 25046.0000000,
 -2631062.5000000, 4037.8200684, 5112.6118164, 18005.9648438, 0.0101010,
 0.0000000, 15252.7998047, 3961.2727051 };

/** Defines extracted features MAX scaling factor
 */
static const nrf_user_feature_t EXTRACTED_FEATURES_SCALE_MAX[] = {
 9345168.0000000, 18345770.0000000, 25780270.0000000, 9715459.0000000,
 4374659.5000000, 5090206.0000000, 9918490.0000000, 0.5555556, 0.3939394,
 9715459.0000000, 2362827.2500000, 8356932.0000000, 10704291.0000000,
 28981868.0000000, 8552868.0000000, 2656237.0000000, 3628586.5000000,
 9703781.0000000, 0.5858586, 0.1616162, 9703708.0000000, 1530814.0000000,
 9842875.0000000, 36697524.0000000, 42708296.0000000, 10007287.0000000,
 2844687.7500000, 4301463.5000000, 10588473.0000000, 0.5656565, 0.1616162,
 10007287.0000000, 2723721.0000000, -10995.0000000, 3255300.0000000,
 5221063.0000000, 758358.1875000, 994624.0625000, 1310911.1250000,
 1314566.8750000, 0.4141414, 0.3636364, 981103.9375000, 265177.1250000,
 9162.0000000, 5759847.0000000, 9792777.0000000, 785511.1875000,
 1008914.7500000, 1437949.0000000, 1490267.1250000, 0.4242424, 0.2525252,
 993058.7500000, 472976.0000000, 167377.0000000, 7628483.0000000,
 7461106.0000000, 2590574.5000000, 1622501.1250000, 1832488.0000000,
 3037172.0000000, 0.4242424, 0.2323232, 2639944.2500000, 365161.3437500 };

/** Memory allocation to store extracted features during DSP pipeline */
static uint8_t extracted_features_buffer_[EXTRACTED_FEATURES_BUFFER_SIZE_BYTES] __NRF_EDGEAI_ALIGNED;


/** Timedomain features processing context  */
#define P_TIMEDOMAIN_FEATURES_CTX  NULL
/** Timedomain features in feature extraction pipeline  */
static const nrf_edgeai_features_pipeline_func_f32_t timedomain_features_[] = {
    nrf_edgeai_feature_utility_tss_sum_f32,
    nrf_edgeai_feature_min_max_range_f32,
    nrf_edgeai_feature_mean_f32,
    nrf_edgeai_feature_mad_f32,
    nrf_edgeai_feature_std_f32,
    nrf_edgeai_feature_rms_f32,
    nrf_edgeai_feature_mcr_f32,
    nrf_edgeai_feature_zcr_f32,
    nrf_edgeai_feature_absmean_f32,
    nrf_edgeai_feature_amdf_f32
 };

static const nrf_edgeai_features_pipeline_ctx_t timedomain_pipeline_ = {
    .functions_num     = sizeof(timedomain_features_) / sizeof(timedomain_features_[0]),
    .functions.p_void  = timedomain_features_,
    .p_ctx             = P_TIMEDOMAIN_FEATURES_CTX,
};
#define P_TIMEDOMAIN_PIPELINE &timedomain_pipeline_ 

#define P_FREQDOMAIN_PIPELINE NULL

#define P_CUSTOMDOMAIN_PIPELINE NULL

static nrf_edgeai_dsp_pipeline_t dsp_pipeline_ = { 
   .features = {  
       .p_masks = (const nrf_edgeai_features_mask_t*)FEATURES_EXTRACTION_MASK, 
       .buffer.p_void = extracted_features_buffer_, 
       .overall_num = EXTRACTED_FEATURES_NUM, 
       .masks_num = sizeof(FEATURES_EXTRACTION_MASK) / sizeof(FEATURES_EXTRACTION_MASK[0]), 

       .p_timedomain_pipeline = P_TIMEDOMAIN_PIPELINE, 
       .p_freqdomain_pipeline = P_FREQDOMAIN_PIPELINE, 
       .p_customdomain_pipeline = P_CUSTOMDOMAIN_PIPELINE, 

       .meta.EXTRACTED_FEATURES_META_TYPE = { 
           .p_min = EXTRACTED_FEATURES_SCALE_MIN, 
           .p_max = EXTRACTED_FEATURES_SCALE_MAX, 
       .p_arguments = FEATURES_EXTRACTION_ARGUMENTS, 
       },
   }, 
}; 

#define P_DSP_PIPELINE         &dsp_pipeline_ 


//////////////////////////////////////////////////////////////////////////////
#define NN_INPUT_INIT_INTERFACE        nrf_edgeai_input_init_sliding_window 
#define NN_INPUT_FEED_INTERFACE        nrf_edgeai_input_feed_sliding_window_f32 
#define NN_PROCESS_FEATURES_INTERFACE  nrf_edgeai_process_features_dsp_f32_f32 
#define NN_INIT_INFERENCE_INTERFACE    nrf_edgeai_init_inference_axon 
#define NN_RUN_INFERENCE_INTERFACE     nrf_edgeai_run_inference_axon 
#define NN_PROPAGATE_OUTPUTS_INTERFACE nrf_edgeai_output_dequantize_axon_q8_f32 
#define NN_DECODE_OUTPUTS_INTERFACE    nrf_edgeai_output_decode_classification_f32 

//////////////////////////////////////////////////////////////////////////////

static nrf_user_output_t model_outputs_[MODEL_OUTPUTS_NUM];

//////////////////////////////////////////////////////////////////////////////

static nrf_edgeai_t nrf_edgeai_ = {
    ///
    .metadata.p_solution_id     = EDGEAI_LAB_SOLUTION_ID_STR,
    .metadata.version.combined  = EDGEAI_RUNTIME_VERSION_COMBINED,
    ///   
    .input.p_used_for_lags_mask = INPUT_FEATURES_USED_FOR_LAGS_MASK,
    .input.p_usage_mask         = INPUT_FEATURES_USAGE_MASK,
    .input.type                 = INPUT_FEATURE_DATA_TYPE,
    .input.unique_num           = INPUT_UNIQ_FEATURES_NUM,
    .input.unique_num_used      = INPUT_UNIQ_FEATURES_USED_NUM,
    .input.unique_scales_num    = INPUT_UNIQUE_SCALES_NUM,
    .input.window_size          = INPUT_WINDOW_SIZE,
    .input.window_shift         = INPUT_WINDOW_SHIFT,
    .input.subwindow_num        = INPUT_SUBWINDOW_NUM,
    .input.window_memory.p_void = INPUT_WINDOW_MEMORY,
    .input.p_window_ctx         = P_INPUT_WINDOW_CTX,

    .input.scale.INPUT_TYPE = {
        .p_min = INPUT_FEATURES_SCALE_MIN,
        .p_max = INPUT_FEATURES_SCALE_MAX,
    }, 
    ///
    .p_dsp = P_DSP_PIPELINE,
    ///
    .model.type                 = (nrf_edgeai_model_type_t)MODEL_TYPE,
    .model.task                 = (nrf_edgeai_model_task_t)MODEL_TASK,
    .model.instance.p_void      = P_MODEL_INSTANCE,
    .model.output.memory.p_void = model_outputs_,
    .model.output.num           = MODEL_OUTPUTS_NUM,
    .model.uses_as_input.all    = MODEL_USES_AS_INPUT_MASK,
    ///
    .interfaces.input_init          = NN_INPUT_INIT_INTERFACE,
    .interfaces.feed_inputs         = NN_INPUT_FEED_INTERFACE,
    .interfaces.process_features    = NN_PROCESS_FEATURES_INTERFACE,
    .interfaces.init_inference      = NN_INIT_INFERENCE_INTERFACE,
    .interfaces.run_inference       = NN_RUN_INFERENCE_INTERFACE,
    .interfaces.propagate_outputs   = NN_PROPAGATE_OUTPUTS_INTERFACE,
    .interfaces.decode_outputs      = NN_DECODE_OUTPUTS_INTERFACE,
    ///
    .decoded_output = { NN_DECODED_OUTPUT_INIT },
};

//////////////////////////////////////////////////////////////////////////////

nrf_edgeai_t* nrf_edgeai_user_model_95957(void)
{
    return &nrf_edgeai_;
}

//////////////////////////////////////////////////////////////////////////////

uint32_t nrf_edgeai_user_model_size_95957(void)
{
    uint32_t model_size = 0;

#if MODEL_TYPE == __NRF_EDGEAI_MODEL_NEUTON
    model_size +=
        (sizeof(MODEL_WEIGHTS) + sizeof(MODEL_NEURONS_LINKS) +
         sizeof(MODEL_NEURON_EXTERNAL_LINKS_NUM) + sizeof(MODEL_NEURON_INTERNAL_LINKS_NUM) +
         sizeof(MODEL_NEURON_ACTIVATION_WEIGHTS) + sizeof(MODEL_NEURON_ACTIVATION_TYPE_MASK) +
         sizeof(MODEL_OUTPUT_NEURONS_INDICES));

#if MODEL_TASK == __NRF_EDGEAI_TASK_ANOMALY_DETECTION
    model_size += sizeof(MODEL_AVERAGE_EMBEDDING) + sizeof(MODEL_OUTPUT_SCALE_MIN) +
                  sizeof(MODEL_OUTPUT_SCALE_MAX);
#endif

#if MODEL_TASK == __NRF_EDGEAI_TASK_REGRESSION
    model_size += sizeof(MODEL_OUTPUT_SCALE_MIN) + sizeof(MODEL_OUTPUT_SCALE_MAX);
#endif

#elif MODEL_TYPE == __NRF_EDGEAI_MODEL_AXON
    const nrf_axon_nn_compiled_model_s* p_axon_model = P_MODEL_INSTANCE;

    model_size += sizeof(*p_axon_model);
    model_size += p_axon_model->model_const_size;
    model_size += p_axon_model->cmd_buffer_len * sizeof(NRF_AXON_PLATFORM_BITWIDTH_UNSIGNED_TYPE);

    if (p_axon_model->persistent_vars.buf_ptr != NULL)
    {
        model_size +=
            sizeof(nrf_axon_nn_model_persistent_var_s) * p_axon_model->persistent_vars.count;
    }

#endif

    return model_size;
}


