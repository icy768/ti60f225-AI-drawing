# Local evidence collection sequence

The first read-only collector expected BIT/HEX immediately after PnR and exited on the missing-file assertion (collector_stderr.log). PnR itself completed successfully; it produces the routed logical bitstream but does not run programming-file generation in this flow. No PnR rerun was needed.

The separate local `efx_run ... --flow pgm` programming-file generator completed rc0 after resource/timing gates passed, followed by final evidence collection rc0. `--flow pgm` generates local files; device I/O is a different `program` flow, which was never called. BITFILE_QUEUE.json and final_collector_stdout.log record the successful completion. No healthy background job was stopped and no board was programmed.
