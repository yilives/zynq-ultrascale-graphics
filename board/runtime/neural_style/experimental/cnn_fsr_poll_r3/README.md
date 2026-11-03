# Cached read-clear FSR completion

`fsr_polled.hpp` extends the owned command lifecycle with a nonblocking
`ready()`. AP_DONE is read-clear: the first observation is latched in the owner,
repeat queries do not read hardware again, and `finish()` validates the return
value and tag before POST submission. A completed but unretired command still
owns its output bank and rejects a new command.

The generated runtime checks completion after the next CNN core wait and every
128 acknowledged output groups. Its callback runs only on the main thread and
is cleared before captured resources are destroyed. Existing AXI drain,
quarantine, bank ownership and snapshot rules are preserved.

`test_polled.cpp` contains the original lifecycle tests plus cached-DONE cases
(145 checks). Static board tests query ready repeatedly before finish; live
tests include SIGTERM after a cached DONE and full output hash verification.

Generation/build: `scripts/prepare_cnn_fsr_pipe_r3.py` and
`scripts/build_cnn_fsr_pipe_r3.sh`. Candidate files are additive and the
generators refuse to overwrite an existing candidate directory.

See `docs/CNN_FSR_NOTIFY_2026-11-02.md` for the same-hole ABCCBA result
(46.68 to 50.70 FPS), timing semantics, artifacts and remaining costs.
