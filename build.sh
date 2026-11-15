#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
#
# Build the Redmi Note 13 4G (sapphire / sapphiren, SM6225 "khaje") device
# trees: the base DTBs that go into vendor_boot and the dtbo.img overlays.
#
# This mirrors what Qualcomm's kernel platform build does:
#   1. compile the kernel tree (qcom/) and the "techpack" trees
#      (display/, camera/, audio/, video/, graphics/, wlan/, bt/, touch/)
#      with cpp + dtc -@ (same flags as kernel scripts/Makefile.lib),
#   2. merge them like kernel_platform/build/android/merge_dtbs.py does:
#      base DTB  = fdtoverlay(kernel base, techpack base overlays...)
#      board DTBO = fdtoverlaymerge(kernel board overlay, techpack overlays...)
#      (the merge plan is explicit here, see the tables below, instead of
#      being guessed from msm-id/board-id intersections),
#   3. dtb.img = concatenation of the base DTBs,
#      dtbo.img = mkdtboimg.py create (page size 4096, id/rev/custom = 0).
#
# Tools needed: gcc (cpp), dtc/fdtoverlay/fdtoverlaymerge/fdtput from the
# Qualcomm dtc fork (CLO kernel_platform/external/dtc; fdtoverlaymerge is
# not in upstream dtc), python3, mkdtboimg.py (AOSP system/libufdt).
set -euo pipefail

TOP=$(cd "$(dirname "$0")" && pwd)
KERNEL_DIR=${KERNEL_DIR:-$TOP/../kernel_platform/msm-kernel}
CAMERA_KERNEL_DIR=${CAMERA_KERNEL_DIR:-$TOP/../vendor/qcom/opensource/camera-kernel}
QDTC=${QDTC:-/home/angel/sapphire/srcpool/_tools/k6/qdtc}
DTC=${DTC:-$QDTC/dtc}
FDTOVERLAY=${FDTOVERLAY:-$QDTC/fdtoverlay}
FDTOVERLAYMERGE=${FDTOVERLAYMERGE:-$QDTC/fdtoverlaymerge}
FDTPUT=${FDTPUT:-$QDTC/fdtput}
MKDTBOIMG=${MKDTBOIMG:-/home/angel/sapphire/srcpool/_tools/k6/libufdt/utils/src/mkdtboimg.py}
OUT=${OUT:-$TOP/out}
EXTRA_DTC_FLAGS=${EXTRA_DTC_FLAGS:-}

DTC_INCLUDE="$KERNEL_DIR/scripts/dtc/include-prefixes"
DTC_FLAGS="-Wno-interrupt_provider -Wno-unit_address_vs_reg \
 -Wno-unit_address_format -Wno-avoid_unnecessary_addr_size -Wno-alias_paths \
 -Wno-graph_child_address -Wno-simple_bus_reg -Wno-unique_unit_address -@ \
 $EXTRA_DTC_FLAGS"

mkdir -p "$OUT/obj" "$OUT/merged"

# compile <source.dts> <output> : cpp + dtc, like the kernel's cmd_dtc
compile() {
	local src=$TOP/$1 out=$OUT/obj/$2 dir
	dir=$(dirname "$src")
	mkdir -p "$(dirname "$out")"
	gcc -E -nostdinc -I"$DTC_INCLUDE" -I"$dir" -I"$TOP/qcom" \
		-I"$CAMERA_KERNEL_DIR" -undef -D__DTS__ -x assembler-with-cpp \
		-o "$out.pre" "$src"
	# shellcheck disable=SC2086
	"$DTC" -q -O dtb -o "$out" -b 0 -i "$dir" -i "$DTC_INCLUDE" $DTC_FLAGS \
		"$out.pre"
}

# ---------------------------------------------------------------- sources
# kernel tree
compile qcom/khaje.dts                      qcom/khaje.dtb
compile qcom/sapphire-overlay.dts           qcom/sapphire-overlay.dtbo
compile qcom/sapphiren-overlay.dts          qcom/sapphiren-overlay.dtbo
# techpack base overlays (applied onto the base DTB)
compile video/khaje-vidc.dts                video/khaje-vidc.dtbo
compile camera/khaje-camera.dts             camera/khaje-camera.dtbo
compile wlan/khaje-wlan.dts                 wlan/khaje-wlan.dtbo
compile audio/khaje-audio.dts               audio/khaje-audio.dtbo
compile graphics/khaje-gpu.dts              graphics/khaje-gpu.dtbo
compile display/khaje-sde.dts               display/khaje-sde.dtbo
compile bt/khaje-bt.dts                     bt/khaje-bt.dtbo
# techpack board overlays for sapphire/sapphiren
compile camera/sapphire-camera-sensor.dts   camera/sapphire-camera-sensor.dtbo
compile audio/sapphire-audio-overlay.dts    audio/sapphire-audio-overlay.dtbo
compile display/sapphire-sde-display-overlay.dts display/sapphire-sde-display-overlay.dtbo
compile touch/sapphire-touch-overlay.dts    touch/sapphire-touch-overlay.dtbo

# ---------------------------------------------------------------- merge
O=$OUT/obj
M=$OUT/merged
# base DTB: techpacks applied in the same order as the stock build
KHAJE_TECHPACKS="$O/video/khaje-vidc.dtbo $O/camera/khaje-camera.dtbo \
 $O/wlan/khaje-wlan.dtbo $O/audio/khaje-audio.dtbo $O/graphics/khaje-gpu.dtbo \
 $O/display/khaje-sde.dtbo $O/bt/khaje-bt.dtbo"
# shellcheck disable=SC2086
"$FDTOVERLAY" -i "$O/qcom/khaje.dtb" -o "$M/khaje.dtb" $KHAJE_TECHPACKS
# merge_dtbs.py splits khaje (msm-id 518 + 586) into one DTB per msm-id
cp "$M/khaje.dtb" "$M/khaje-518.dtb"; "$FDTPUT" -t i "$M/khaje-518.dtb" / qcom,msm-id 518 65536
cp "$M/khaje.dtb" "$M/khaje-586.dtb"; "$FDTPUT" -t i "$M/khaje-586.dtb" / qcom,msm-id 586 65536

SAPPHIRE_TECHPACKS="$O/camera/sapphire-camera-sensor.dtbo \
 $O/audio/sapphire-audio-overlay.dtbo $O/display/sapphire-sde-display-overlay.dtbo \
 $O/touch/sapphire-touch-overlay.dtbo"
# shellcheck disable=SC2086
"$FDTOVERLAYMERGE" -i "$O/qcom/sapphire-overlay.dtbo" -o "$M/sapphire.dtbo" \
	$SAPPHIRE_TECHPACKS 2>/dev/null
# shellcheck disable=SC2086
"$FDTOVERLAYMERGE" -i "$O/qcom/sapphiren-overlay.dtbo" -o "$M/sapphiren.dtbo" \
	$SAPPHIRE_TECHPACKS 2>/dev/null

echo "build.sh: done ($M)"
