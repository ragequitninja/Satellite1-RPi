# sys-packages/satellite1-xmos-firmware/Makefile

PACKAGE_NAME       ?= satellite1-xmos-firmware
FIRMWARE_VERSION   ?= 0.0.0
ARCH               ?= arm64

OUT_DIR            ?= ${PWD}/out
DEB_FILE           := $(PACKAGE_NAME)_$(FIRMWARE_VERSION)_$(ARCH).deb

BUILD_DIR          := ${PWD}/build
DEBIAN_DIR         := ${BUILD_DIR}/debian
BUILD_FW_DIR       := ${BUILD_DIR}/firmware

FW_BASENAME        := xmos-$(FIRMWARE_VERSION).bin
FW_MANIFEST        := xmos-$(FIRMWARE_VERSION).json
FW_SHA256          := xmos-$(FIRMWARE_VERSION).sha256

THIS_MAKEFILE      := $(abspath $(lastword $(MAKEFILE_LIST)))
MAKE_DIR           := $(dir $(THIS_MAKEFILE))
SRC_DEBIAN_DIR     := $(MAKE_DIR)/debian
SRC_CONTROL_IN     := $(SRC_DEBIAN_DIR)/control.in
SRC_POSTINST_IN    := $(SRC_DEBIAN_DIR)/postinst.in
SRC_INSTALL_IN     := $(SRC_DEBIAN_DIR)/install.in
SRC_CHANGELOG_IN   := $(SRC_DEBIAN_DIR)/changelog.in

FIRMWARE_BIN       ?= $(MAKE_DIR)/firmware/xmos-firmware.bin

DOCKER             ?= docker
PLATFORM           ?= linux/arm64
DOCKER_IMAGE       ?= satellite1-deb-builder

.PHONY: all deb image clean distclean print-config help

all: deb

help:
	@echo "Targets:"
	@echo "  make deb                                  Build firmware .deb inside Docker"
	@echo "  make image                                Build shared deb-builder Docker image"
	@echo "  make clean                                Remove build/ and out/"
	@echo "  make print-config                         Show active build configuration"
	@echo
	@echo "Variables (override with make VAR=value):"
	@echo "  FIRMWARE_VERSION=0.0.0"
	@echo "  FIRMWARE_BIN=firmware/xmos-firmware.bin"
	@echo "  OUT_DIR=..."

print-config:
	@echo "PACKAGE_NAME     = $(PACKAGE_NAME)"
	@echo "FIRMWARE_VERSION = $(FIRMWARE_VERSION)"
	@echo "ARCH             = $(ARCH)"
	@echo "FIRMWARE_BIN     = $(FIRMWARE_BIN)"
	@echo "OUT_DIR          = $(OUT_DIR)"
	@echo "DOCKER_IMAGE     = $(DOCKER_IMAGE)"

deb: image $(DEB_FILE)

image:
	$(MAKE) -C ../../docker deb-image

$(DEB_FILE): $(DEBIAN_DIR)/changelog $(DEBIAN_DIR)/control $(DEBIAN_DIR)/postinst $(DEBIAN_DIR)/$(PACKAGE_NAME).install $(BUILD_FW_DIR)/$(FW_BASENAME) $(BUILD_FW_DIR)/$(FW_MANIFEST) $(BUILD_FW_DIR)/$(FW_SHA256)
	mkdir -p "$(OUT_DIR)"
	echo "*" > "$(OUT_DIR)/.gitignore"
	$(DOCKER) run --rm --platform=$(PLATFORM) \
	  -v "$(BUILD_DIR)":/work/src \
	  -v "$(OUT_DIR)":/out \
	  -w /work/src \
	  $(DOCKER_IMAGE) \
	  bash -lc 'dpkg-buildpackage -b -us -uc && cp ../*.deb /out'
	@echo
	@echo "Built firmware package: $(DEB_FILE)"

$(DEBIAN_DIR)/control: $(SRC_CONTROL_IN) | $(DEBIAN_DIR)
	sed \
	  -e 's/@PACKAGE_NAME@/$(PACKAGE_NAME)/g' \
	  -e 's/@VERSION@/$(FIRMWARE_VERSION)/g' \
	  -e 's/@ARCH@/$(ARCH)/g' \
	  "$<" > "$@"

$(DEBIAN_DIR)/changelog: $(SRC_CHANGELOG_IN) | $(DEBIAN_DIR)
	@DATE_R="$$(LC_ALL=C date -R)"; \
	  sed \
	    -e 's/@PACKAGE_NAME@/$(PACKAGE_NAME)/g' \
	    -e 's/@VERSION@/$(FIRMWARE_VERSION)/g' \
	    -e "s|@DATE_R@|$$DATE_R|g" \
	    "$<" > "$@"

$(DEBIAN_DIR)/postinst: $(SRC_POSTINST_IN) | $(DEBIAN_DIR)
	sed \
	  -e 's/@FW_BASENAME@/$(FW_BASENAME)/g' \
	  -e 's/@FW_MANIFEST@/$(FW_MANIFEST)/g' \
	  -e 's/@FW_SHA256@/$(FW_SHA256)/g' \
	  "$<" > "$@"
	chmod 0755 "$@"

$(DEBIAN_DIR)/$(PACKAGE_NAME).install: $(SRC_INSTALL_IN) | $(DEBIAN_DIR)
	sed \
	  -e 's/@FW_BASENAME@/$(FW_BASENAME)/g' \
	  -e 's/@FW_MANIFEST@/$(FW_MANIFEST)/g' \
	  -e 's/@FW_SHA256@/$(FW_SHA256)/g' \
	  "$<" > "$@"

$(BUILD_FW_DIR)/$(FW_BASENAME): $(FIRMWARE_BIN) | $(BUILD_FW_DIR)
	@test -f "$<" || { echo "ERROR: firmware file not found: $<"; exit 10; }
	cp "$<" "$@"

$(BUILD_FW_DIR)/$(FW_SHA256): $(BUILD_FW_DIR)/$(FW_BASENAME)
	cd "$(BUILD_FW_DIR)" && sha256sum "$(FW_BASENAME)" > "$(FW_SHA256)"

$(BUILD_FW_DIR)/$(FW_MANIFEST): $(BUILD_FW_DIR)/$(FW_BASENAME)
	@SHA256="$$(sha256sum "$(BUILD_FW_DIR)/$(FW_BASENAME)" | awk '{print $$1}')"; \
	printf '{\n  "version": "$(FIRMWARE_VERSION)",\n  "file": "$(FW_BASENAME)",\n  "sha256": "%s",\n  "target": "xmos"\n}\n' "$$SHA256" > "$@"

$(DEBIAN_DIR):
	mkdir -p "$(BUILD_DIR)"
	echo "*" > "$(BUILD_DIR)/.gitignore"
	cp -r "$(SRC_DEBIAN_DIR)" "$(BUILD_DIR)"

$(BUILD_FW_DIR):
	mkdir -p "$(BUILD_FW_DIR)"

clean:
	rm -rf "$(BUILD_DIR)" "$(OUT_DIR)"

distclean: clean
	@echo "Nothing extra to distclean."
