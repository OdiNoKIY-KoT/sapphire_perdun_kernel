#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
#
# Build the Redmi Note 13 4G (sapphire / sapphiren, SM6225 "khaje") device
# trees: the base DTBs that go into vendor_boot and the dtbo.img overlays.
#
# This mirrors what Qualcomm's kernel platform build does:
#   1. compile the kernel tree (qcom/) and the "techpack" trees
#      (video/ camera/ wlan/ audio/ graphics/ display/ bt/) with cpp +
#      dtc -@ (same flags as kernel scripts/Makefile.lib),
#   2. merge them like kernel_platform/build/android/merge_dtbs.py does:
#        base DTB   = fdtoverlay(kernel base DTB, techpack base overlays...)
#        board DTBO = fdtoverlaymerge(kernel board overlay, techpack overlays...)
#      The merge plan is spelled out below instead of being derived from the
#      msm-id/board-id intersections, and reproduces the stock layout:
#      khaje.dtb is emitted once per msm-id (518, 586) like merge_dtbs.py,
#      and techpacks are applied in the stock order.
#   3. dtb.img  = concatenation of the base DTBs (vendor_boot "dtb" section)
#      dtbo.img = mkdtboimg.py create, page size 4096, id/rev/custom = 0
#      (same as stock).
#
# Entries for the Qualcomm reference boards (ATP/IDP/QRD/... of the other
# khaje SKUs) are built from reference/*.dts, so that dtb.img/dtbo.img keep
# the same 6 + 47 entries as stock.
#
# Usage: ./build.sh [OUT=dir] ; env overrides: KERNEL_DIR, CAMERA_KERNEL_DIR,
#        DTC, FDTOVERLAY, FDTOVERLAYMERGE, FDTPUT, MKDTBOIMG
#
# Tools: gcc (cpp), python3, dtc/fdtoverlay/fdtoverlaymerge/fdtput from the
# Qualcomm dtc fork (CLO kernel_platform/external/dtc, branch
# kernel.build.lnx.1.0.r10-rel; fdtoverlaymerge is not in upstream dtc),
# mkdtboimg.py (AOSP system/libufdt/utils/src).
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

DTC_INCLUDE="$KERNEL_DIR/scripts/dtc/include-prefixes"
DTC_FLAGS="-Wno-interrupt_provider -Wno-unit_address_vs_reg \
 -Wno-unit_address_format -Wno-avoid_unnecessary_addr_size -Wno-alias_paths \
 -Wno-graph_child_address -Wno-simple_bus_reg -Wno-unique_unit_address -@"

O=$OUT/obj
M=$OUT/merged
rm -rf "$O" "$M"
mkdir -p "$O" "$M"

# compile <source.dts> : cpp + dtc like the kernel's cmd_dtc; -> $O/<path>.dtb[o]
compile() {
	local src=$TOP/$1 ext out dir
	# overlays (/plugin/) -> .dtbo, except reference/*-dtb.dts which the
	# stock build shipped as a .dtb in vendor_boot (khajep-qrd-overlay)
	if grep -q '^/plugin/;' "$src" && [[ "$1" != *-dtb.dts ]]; then ext=dtbo; else ext=dtb; fi
	out=$O/${1%.dts}.$ext
	dir=$(dirname "$src")
	mkdir -p "$(dirname "$out")"
	gcc -E -nostdinc -I"$DTC_INCLUDE" -I"$dir" -I"$TOP/qcom" \
		-I"$CAMERA_KERNEL_DIR" -undef -D__DTS__ -x assembler-with-cpp \
		-o "$out.pre" "$src"
	# shellcheck disable=SC2086
	"$DTC" -q -O dtb -o "$out" -b 0 -i "$dir" -i "$DTC_INCLUDE" $DTC_FLAGS "$out.pre"
	rm -f "$out.pre"
}

# ------------------------------------------------------------------ compile
SOURCES="qcom/khaje.dts
qcom/sapphire-overlay.dts
qcom/sapphiren-overlay.dts
video/khaje-vidc.dts
camera/khaje-camera.dts
wlan/khaje-wlan.dts
audio/khaje-audio.dts
graphics/khaje-gpu.dts
display/khaje-sde.dts
bt/khaje-bt.dts
camera/sapphire-camera-sensor.dts
audio/sapphire-audio-overlay.dts
display/sapphire-sde-display-overlay.dts"
for s in $SOURCES; do compile "$s"; done
if [ -d "$TOP/reference" ]; then
	for s in "$TOP"/reference/*.dts; do compile "reference/$(basename "$s")"; done
fi

# ------------------------------------------------------------------ merge
# base DTB: techpack base overlays, in the order the stock build applied them
KHAJE_TECHPACKS="$O/video/khaje-vidc.dtbo $O/camera/khaje-camera.dtbo \
 $O/wlan/khaje-wlan.dtbo $O/audio/khaje-audio.dtbo $O/graphics/khaje-gpu.dtbo \
 $O/display/khaje-sde.dtbo $O/bt/khaje-bt.dtbo"
# shellcheck disable=SC2086
"$FDTOVERLAY" -i "$O/qcom/khaje.dtb" -o "$M/khaje.dtb" $KHAJE_TECHPACKS
for id in 518 586; do
	cp "$M/khaje.dtb" "$M/khaje-$id.dtb"
	"$FDTPUT" -t i "$M/khaje-$id.dtb" / qcom,msm-id "$id" 65536
done

# board overlays: kernel overlay + camera, audio, display(+touch) techpacks
SAPPHIRE_TECHPACKS="$O/camera/sapphire-camera-sensor.dtbo \
 $O/audio/sapphire-audio-overlay.dtbo $O/display/sapphire-sde-display-overlay.dtbo"
for b in sapphire sapphiren; do
	# shellcheck disable=SC2086
	"$FDTOVERLAYMERGE" -i "$O/qcom/$b-overlay.dtbo" -o "$M/$b.dtbo" \
		$SAPPHIRE_TECHPACKS >/dev/null 2>&1
done

# ------------------------------------------------------------------ images
# Same entry order as the stock images (see reference/ENTRIES).
DTB_LIST="$M/khaje-518.dtb $M/khaje-586.dtb"
DTBO_LIST=""
if [ -f "$TOP/reference/ENTRIES" ]; then
	DTB_LIST=""
	while read -r kind name; do
		case "$kind" in
		dtb)  case "$name" in
			khaje-518|khaje-586) DTB_LIST="$DTB_LIST $M/$name.dtb" ;;
			*) DTB_LIST="$DTB_LIST $O/reference/$name.dtb" ;;
			esac ;;
		dtbo) case "$name" in
			sapphire|sapphiren) DTBO_LIST="$DTBO_LIST $M/$name.dtbo" ;;
			*) DTBO_LIST="$DTBO_LIST $O/reference/$name.dtbo" ;;
			esac ;;
		esac
	done < <(grep -v '^#' "$TOP/reference/ENTRIES")
else
	DTBO_LIST="$M/sapphire.dtbo $M/sapphiren.dtbo"
fi
# shellcheck disable=SC2086
cat $DTB_LIST > "$OUT/dtb.img"
# shellcheck disable=SC2086
python3 "$MKDTBOIMG" create "$OUT/dtbo.img" --page_size=4096 $DTBO_LIST
echo "build.sh: $OUT/dtb.img ($(echo $DTB_LIST | wc -w) DTBs), $OUT/dtbo.img ($(echo $DTBO_LIST | wc -w) entries)"
