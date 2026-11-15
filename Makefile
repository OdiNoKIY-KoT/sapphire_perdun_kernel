# Thin wrapper around build.sh / tools/verify.sh (see README.md)
STOCK_DTB  ?= /home/angel/sapphire/unpacked/vendor_boot/dtb
STOCK_DTBO ?= /home/angel/sapphire/fw/dtbo.img

all:
	./build.sh

verify: all
	tools/verify.sh $(STOCK_DTB) $(STOCK_DTBO)

clean:
	rm -rf out

.PHONY: all verify clean
