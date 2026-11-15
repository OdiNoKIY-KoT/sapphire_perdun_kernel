# Redmi Note 13 4G (sapphire / sapphiren) device tree sources

SoC: Qualcomm SM6225 "khaje" (bengal family), kernel 5.15 (KERNEL.PLATFORM 2.0).
Builds the vendor_boot DTB list (6 DTBs) and `dtbo.img` (47 entries; #45 =
sapphire, board-id 0x20022; #46 = sapphiren/NFC, board-id 0x30022) so that they
are semantically identical to the stock HyperOS OS2.0.215.0.VNHEUXM images.

    ./build.sh                       # -> out/dtb.img, out/dtbo.img, out/merged/*
    tools/verify.sh STOCK_DTB STOCK_DTBO_IMG   # equivalence check vs stock

`build.sh` needs the kernel tree (`KERNEL_DIR`, for `dt-bindings`), the camera
kernel tree (`CAMERA_KERNEL_DIR`, for `dt-bindings/msm-camera.h`), the Qualcomm
dtc fork (`dtc`, `fdtoverlay`, `fdtoverlaymerge`, `fdtput`; CLO
`kernel_platform/external/dtc`, branch `kernel.build.lnx.1.0.r10-rel`) and
AOSP `mkdtboimg.py`. NOTE: `io-channels` use `PSY_IIO_*` from
`include/dt-bindings/iio/qti_power_supply_iio.h`, which must carry the stock
(sapphire) numbering, as the one in this workspace's msm-kernel does.

## Layout and provenance

| path | content | origin |
|---|---|---|
| `qcom/khaje*.dts*`, `bengal-*`, `pm6125*`, `pm8008`, `khaje-usb/-pinctrl/-regulator/-dma-heaps`, `msm-*` | SoC base (kernel tree) | MiCode `kernel_devicetree` creek-v-oss (GPL), edited to the stock sapphire SoC tree (see git log) |
| `qcom/sapphire-overlay.dts`, `qcom/sapphiren-overlay.dts`, `qcom/sapphire-*.dtsi`, `qcom/qg-batterydata-*.dtsi` | sapphire board: thermal, fingerprint, keys, storage, PM7250B/SMB5/QG, battery auth, charge pumps (SC8541/BQ25960), CP manager, NFC (sapphiren) | reconstructed from stock dtbo #45/#46 (no public source) |
| `display/khaje-sde*.dts*` | display techpack base | MiCode `display-devicetree` creek-v-oss, edited |
| `display/dsi*panel*.dtsi`, `display/sapphire-*` | panels (m7_38_0c_0a/0b, n7_38_0c_0a + QC reference panels), touch | reconstructed from stock |
| `camera/khaje-camera.dts*` | camera techpack base | MiCode `camera-devicetree` creek-v-oss |
| `camera/sapphire-camera-sensor.dts*` | sapphire sensors/actuator/EEPROM/flash | reconstructed from stock |
| `audio/`, `video/`, `graphics/`, `wlan/`, `bt/` | Qualcomm techpack overlays (unpublished) | reconstructed from stock |
| `reference/` | the 45 other dtbo entries (Qualcomm ATP/IDP/QRD boards of khaje/khajeg/khajep/khajeq) and the stray `khajep-qrd-overlay` blob in vendor_boot | machine-generated from stock by `tools/mkreference.py` |
| `tools/` | `dtcompare.py` (semantic comparator), `dt2src.py` (DTB/DTBO -> labelled DTS), `verify.sh`, helpers | new |

"Reconstructed" sources were produced from the stock binaries with
`tools/dt2src.py` (labels from `__symbols__`, references from
`__fixups__`/`__local_fixups__`, clock/interconnect/IRQ/PSY_IIO macros
restored) and organised by subsystem; they are verified, not guessed.

## Equivalence

`tools/verify.sh` compares every entry: base DTBs node/property-wise with
phandle cells resolved to node paths (exact reference positions from a `dtc
-L` build of our sources plus the applied overlays), overlays after
normalising fragments/targets/fixups, and the bootloader view (dtbo #45/#46
applied onto both khaje DTBs with fdtoverlay). Current result: all 6 DTBs,
all 47 DTBO entries and the 4 applied combinations are equivalent; 20 DTBO
entries and dtb #3 are even byte-identical. Remaining non-semantic
differences: phandle numbering of a few nodes, node/property order, FDT
string-table layout.
