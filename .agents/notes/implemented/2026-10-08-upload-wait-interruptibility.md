# Upload wait loops must run in a child console process

Status: implemented

## Context

`pio run -t upload` for `upload_protocol = nrfutil-mcumgr` (XIAO nRF54LM20B)
could not be interrupted with Ctrl+C on Windows while waiting for the DFU
loader CDC (60 s) or for a busy port to be released (PR #100). Measured root
cause: SCons executes task actions in a worker thread, CPython only raises
KeyboardInterrupt on the main thread, and the SCons main thread stays parked
in an uninterruptible `Thread.join()` for the whole task; SCons additionally
replaces the SIGINT handler with a non-raising one. No layer of the
pio -> scons -> action chain can react, so in-process wait loops are
uninterruptible by construction.

The STM32 UF2 path was always interruptible because its wait loop lives in
`uf2upload.py`, a child console process: children attached to the console
receive the Ctrl+C event directly and a plain Python child dies on it
instantly (nrfutil itself also dies by default, verified).

## Decision

Upload orchestration that contains waits (port resolution, 1200-bps touch,
loader-CDC poll) runs in a standalone Python child script — for the nRF
family `builder/board_build/nrf/mcumgrupload.py`, spawned as the single
upload action from `nrf_build.py`. Long-running tools it manages (nrfutil)
are waited on with a poll loop so an abort also kills them promptly.

Follow this pattern for any future upload path whose waits would otherwise
run as in-process SCons actions. Note also that `env.Exit(1)` inside an
action raises SystemExit in the worker thread, which SCons's task loop
(only `except Exception`) does not propagate — child scripts exit for real.

## Alternatives considered

- In-process ctypes console-ctrl watchdog (`SetConsoleCtrlHandler` +
  TerminateProcess on the child): rejected — Windows-only, callbacks need
  careful lifetime management, and the repo already had the proven child
  process pattern (uf2upload.py).
- Relying on SCons interrupt handling (`-j 1` Serial mode): rejected — only
  helps loops running on the main thread, and the default job count is the
  CPU count; transfer phases in children already worked.

## Consequences

- The nRF DFU upload aborts in ~0.2 s on Ctrl+C at any wait (measured with
  a console-event injection harness equivalent to a real keypress).
- User-visible messages and exit semantics of the nRF54LM20 DFU path are
  unchanged (busy-port handling and the 9600-bps prime from PR #100 were
  ported verbatim).
- `builder/tools/` stays reserved for the pre-existing generic UF2 helpers;
  family upload scripts live under `builder/board_build/<family>/`.
