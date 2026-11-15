# Thin wrapper around build.sh / tools/verify.sh (see README.md)
# stock references for "make verify": the vendor_boot dtb section and the stock dtbo.img
STOCK_DTB  ?=
STOCK_DTBO ?=

all:
	./build.sh

verify: all
	tools/verify.sh $(STOCK_DTB) $(STOCK_DTBO)

clean:
	rm -rf out

.PHONY: all verify clean
