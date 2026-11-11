P4C ?= p4c-bm2-ss

build/counters.json: p4src/counters.p4
	mkdir -p build
	$(P4C) --p4v 16 -o build/counters.json p4src/counters.p4

.PHONY: all clean
all: build/counters.json

clean:
	rm -rf build
