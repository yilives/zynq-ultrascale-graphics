# Experimental frame mapping, disabled in the delivered runtime

This read-only RFM1 module was tested against the running ARM64 Linux 5.4
kernel. It maps only the 6 MiB PL frame-RAM window, checks the SNP1/NNS1 DT
capabilities and live SNP1 registers, and rejects writing, execution, offsets,
private mappings and different lengths. Control registers remain Device memory.

The matching kernel defines `pgprot_writecombine` as `MT_NORMAL_NC`.
On this board, the controlled single-core test showed no throughput benefit:
Device paired reads and Normal-NC paired reads both took about 48 ms per
307,200 bytes; Normal-NC memcpy was slower. The module was unloaded after the
experiment and is excluded from the runtime archive and automatic startup.
The deployed optimization uses the original Device mapping with four readers.

Sources and evidence: `scripts/build_neural_frame_memory.sh`,
`linux/neural_style/benchmark_frame_memory.cpp`,
`report/neural-style/memory-attributes-benchmark.json`, and
`report/neural-style/parallel-memory-benchmark.json`.

The initial MAP_SHARED test failed because Linux 5.4 clears VM_SHARED for an
O_RDONLY file. The final experiment checks VM_MAYSHARE and was remeasured;
the failed launch is not counted as a successful sample.
