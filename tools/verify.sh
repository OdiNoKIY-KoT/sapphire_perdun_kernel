#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
#
# Equivalence check of the built images against the stock ones.
#
#   tools/verify.sh STOCK_DTB_IMG STOCK_DTBO_IMG [OUT]
#
# STOCK_DTB_IMG : the vendor_boot "dtb" section (concatenated DTBs)
# STOCK_DTBO_IMG: the stock dtbo.img
# OUT           : build output dir (default ./out)
#
# For every entry (same index in stock and ours):
#   * base DTBs   : semantic tree comparison (dtcompare.py base mode); for the
#                   sapphire base the exact phandle-cell positions of our
#                   sources are used (--refs: base compiled with dtc -L +
#                   the techpack overlays applied to it)
#   * DTBO entries: normalised overlay comparison (dtcompare.py overlay mode)
#   * sapphire/sapphiren: additionally the bootloader view, i.e. each DTBO
#                   applied with fdtoverlay onto its base, stock vs ours.
set -u
TOP=$(cd "$(dirname "$0")/.." && pwd)
SDTB=$1
SDTBO=$2
OUT=${3:-$TOP/out}
QDTC=${QDTC:-/home/angel/sapphire/srcpool/_tools/k6/qdtc}
FDTOVERLAY=${FDTOVERLAY:-$QDTC/fdtoverlay}
LDTC=${LDTC:-dtc}       # upstream dtc >= 1.6.1 (needs -L / --local-fixups)
KERNEL_DIR=${KERNEL_DIR:-$TOP/../kernel_platform/msm-kernel}
V=$OUT/verify
rm -rf "$V"; mkdir -p "$V"
T="python3 $TOP/tools"
$T/splitimg.py "$SDTB" "$V/stock" dtb >/dev/null
$T/splitimg.py "$SDTBO" "$V/stock" dtbo >/dev/null
$T/splitimg.py "$OUT/dtb.img" "$V/ours" dtb >/dev/null
$T/splitimg.py "$OUT/dtbo.img" "$V/ours" dtbo >/dev/null

# our base compiled with -L for exact reference positions
gcc -E -nostdinc -I"$KERNEL_DIR/scripts/dtc/include-prefixes" -I"$TOP/qcom" \
	-undef -D__DTS__ -x assembler-with-cpp -o "$V/khaje.pre" "$TOP/qcom/khaje.dts"
"$LDTC" -q -O dtb -b 0 -@ -L -o "$V/khaje-L.dtb" "$V/khaje.pre"
O=$OUT/obj
TPS="$O/video/khaje-vidc.dtbo $O/camera/khaje-camera.dtbo $O/wlan/khaje-wlan.dtbo \
 $O/audio/khaje-audio.dtbo $O/graphics/khaje-gpu.dtbo $O/display/khaje-sde.dtbo $O/bt/khaje-bt.dtbo"

fail=0
report() { # label file
	local res; res=$(head -1 "$2")
	printf "%-34s %s\n" "$1" "$res"
	case "$res" in *"differences=0"*) ;; *) fail=1 ;; esac
}
n=0
for s in "$V"/stock/dtb*.dtb; do
	i=$(basename "$s" .dtb); o=$V/ours/$i.dtb
	if [ "$i" = dtb00 ] || [ "$i" = dtb01 ]; then
		# shellcheck disable=SC2086
		$T/dtcompare.py "$s" "$o" --refs "$V/khaje-L.dtb" $TPS > "$V/$i.txt"
	else
		$T/dtcompare.py "$s" "$o" > "$V/$i.txt"
	fi
	report "vendor_boot $i" "$V/$i.txt"; n=$((n+1))
done
for s in "$V"/stock/dtbo*.dtbo; do
	i=$(basename "$s" .dtbo); o=$V/ours/$i.dtbo
	$T/dtcompare.py "$s" "$o" > "$V/$i.txt"
	report "dtbo $i" "$V/$i.txt"
done
# bootloader view for the device's own entries (dtbo 45/46 on khaje 518/586)
for e in 45 46; do
	for b in 00 01; do
		"$FDTOVERLAY" -i "$V/stock/dtb$b.dtb" -o "$V/s_$b+$e.dtb" "$V/stock/dtbo$e.dtbo"
		"$FDTOVERLAY" -i "$V/ours/dtb$b.dtb" -o "$V/o_$b+$e.dtb" "$V/ours/dtbo$e.dtbo"
		# shellcheck disable=SC2086
		$T/dtcompare.py "$V/s_$b+$e.dtb" "$V/o_$b+$e.dtb" \
			--refs "$V/khaje-L.dtb" $TPS "$V/ours/dtbo$e.dtbo" > "$V/applied_$b+$e.txt"
		report "applied dtb$b + dtbo$e" "$V/applied_$b+$e.txt"
	done
done
[ $fail = 0 ] && echo "verify: ALL EQUIVALENT" || echo "verify: differences found (see $V/*.txt)"
exit $fail
