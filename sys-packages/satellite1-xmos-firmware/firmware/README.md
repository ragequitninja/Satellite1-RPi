Place XMOS firmware binary here before building the package.

Expected default path:
- `sys-packages/satellite1-xmos-firmware/firmware/xmos-firmware.bin`

You can also override the source path at build time:
- `make -C sys-packages/satellite1-xmos-firmware deb FIRMWARE_BIN=/path/to/firmware.bin FIRMWARE_VERSION=1.2.3`

Repository-level shortcuts:
- `make xmos-firmware-deb FIRMWARE_BIN=/path/to/firmware.bin FIRMWARE_VERSION=1.2.3`
- `make xmos-firmware-deb-from-gh XMOS_FW_VERSION=v1.2.3`
