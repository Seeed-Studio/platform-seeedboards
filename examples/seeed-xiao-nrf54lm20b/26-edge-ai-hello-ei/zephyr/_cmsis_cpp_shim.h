#ifndef XIAO_EDGEAI_CMSIS_CPP_SHIM_H
#define XIAO_EDGEAI_CMSIS_CPP_SHIM_H
/*
 * The framework's cmsis_6 (CMSIS/Core/Include/cmsis_gcc.h) defines the CMSIS
 * macros in terms of the BARE compiler intrinsics, e.g.
 *     #define __SXTB16   __sxtb16
 *     #define __SXTAB16  __sxtab16
 * relying on the compiler to provide __sxtb16/__sxtab16 as builtins. GCC (both
 * the framework's 8.2.1 and NCS's 12.2) only exposes these as builtins in C,
 * NOT in C++, so any C++ translation unit that pulls in cmsis_gcc.h fails with
 * "'__sxtb16' was not declared in this scope" (hit by the Edge Impulse SDK).
 *
 * This shim provides those bare names as inline-assembly helpers, but ONLY under
 * __cplusplus, so C translation units keep using the compiler builtins and are
 * unaffected. It is force-included for edge-AI samples only.
 */
#ifdef __cplusplus
#include <stdint.h>

#ifndef __sxtb16
static inline uint32_t __sxtb16(uint32_t x)
{
	uint32_t r;
	__asm__ volatile("sxtb16 %0, %1" : "=r"(r) : "r"(x));
	return r;
}
#endif

#ifndef __sxtab16
static inline uint32_t __sxtab16(uint32_t a, uint32_t b)
{
	uint32_t r;
	__asm__ volatile("sxtab16 %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));
	return r;
}
#endif

#endif /* __cplusplus */
#endif /* XIAO_EDGEAI_CMSIS_CPP_SHIM_H */
