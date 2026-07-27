from SCons.Script import Import


Import("env")
env.Append(
    ASFLAGS=["-mthumb"],
    ASPPFLAGS=["-x", "assembler-with-cpp"],
    CCFLAGS=["-Os", "-ffunction-sections", "-fdata-sections", "-Wall", "-mthumb", "-nostdlib"],
    CXXFLAGS=["-fno-rtti", "-fno-exceptions"],
    CPPDEFINES=[("F_CPU", "$BOARD_F_CPU")],
    LINKFLAGS=["-Os", "-Wl,--gc-sections,--relax", "-mthumb", "--specs=nano.specs", "--specs=nosys.specs"],
    LIBS=["c", "gcc", "m", "stdc++", "nosys"],
)

if "BOARD" in env:
    cpu = env.BoardConfig().get("build.cpu")
    env.Append(
        ASFLAGS=["-mcpu=%s" % cpu],
        CCFLAGS=["-mcpu=%s" % cpu],
        LINKFLAGS=["-mcpu=%s" % cpu],
    )
