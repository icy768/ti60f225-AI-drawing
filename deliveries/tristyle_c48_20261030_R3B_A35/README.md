# DELIVERY_20261030_R3B_A35

A35 (I4 35k FP32 checkpoint, fixed QAT3000) is the user-selected new baseline. The package keeps the frozen C48/Fc16/4-residual/13-layer hardware path and original bitstream, and replaces only the deployed model blob with A35.

## Verification

- A35 checkpoint SHA-256: `f143b273f9de756cbe45321a621b6b6eed3aeaeb4d29f5e2fee712cd85ef0e42`
- Deployed blob SHA-256: `ff96d972e023ff89eaf46b122b319203efd3616f4ee7e07fb5f338fb05c02864`
- CPU int64 640x480: all 3 styles, 13 layers, and final output at 0 LSB.
- RTL 640x8: all 3 styles, 13 layers at 0 LSB using synthetic stimulus; this is not full-size RTL or board verification.
- Original 961-file fallback delivery remains archived as `DELIVERY_20261030_R3B`.

The user directly instructed adoption of A35 as the new baseline. The D8' human blind test package is included and independently verified, but no human answers were supplied; `D8_prime_status` is `NOT_RUN_USER_DIRECT_ADOPTION`. The package records this override explicitly and does not claim a blind-test pass.

Known gaps remain: Van Gogh fidelity is about 0.53, D5 is about 1.19–1.25, and directional thick brush strokes remain unresolved. Board programming, board FPS, SC431HAI, and full-size RTL remain unverified.
