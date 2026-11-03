# Owned asynchronous FSR commands

`fsr_pending.hpp` separates AP command start from completion. It permits the
previous FSR compute to overlap the next CNN while retaining command ownership,
result/tag validation and exception-time AXI draining. Registers and the shared
postprocessing lock must outlive the pending owner. A timeout retains ownership
through the existing fail-stop/quarantine mechanism.

`test_pending.cpp` exercises command ordering, read-clear completion, tag/return
errors, auto-restart rejection, timeout ownership and exception teardown with
fake registers. Real-board tests additionally send SIGTERM immediately after
FSR start 1, 2 and 7 and independently verify the resulting complete images.

The initial late-submission R1 schedules were correct but slower (29.89 FPS).
R2 submits after the next CNN, before ARM fusion (46.89 FPS versus 38.06).
Both remain available in separate `build/neural-style/cnn-fsr-pipe-r*/` folders.

See `docs/CNN_FSR_PIPELINING_2026-11-02.md` for source generation, runtime entry,
timing semantics, acceptance evidence and the remaining display/ARM costs.
