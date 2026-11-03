# Exact native400 fusion candidates

Additive candidates for the accepted CNN + PL FSR runtime. `native400_round.hpp`
factors the bounded exact division; `native400_poly.hpp` additionally specializes
the 160-to-400 horizontal interpolation into its five repeating phases.

Both preserve the existing interpolation, signed rounding, RGB565 luminance
detail correction and explicit source-space protection rectangles. The bounded
reciprocal is valid for this pipeline's [-12800, 12700] numerator range. The
polyphase specialization is for 160x96 to 400x240 only.

Generation: `scripts/prepare_cnn_fsr_fast_r1.py`.
Build: `scripts/build_cnn_fsr_fast_r1.sh` under the existing AArch64 SDK/WSL.
Runtime: `build/neural-style/cnn-fsr-fast-r1/runtime/rix-cfs-poly`.
Board entry: `/tmp/rix-cnn-group-r1/cfs_fast_play.py` (RAM only).

The old runtime, model files, bitstreams and FSR arithmetic are preserved.
See `docs/CNN_FSR_OPTIMIZATION_2026-11-02.md` for measured same-game results,
full-frame hash verification and the remaining serial CNN/FSR bottleneck.
