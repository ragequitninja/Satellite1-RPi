PACKAGE_NAME  ?= satellite1-rpi-sdk
SDK_VERSION   ?= 1.0
ARCH          ?= arm64

ifneq (,$(wildcard .env))
include .env
endif

HOST ?= $(SAT1_HOST)

DOCKER        ?= docker
PLATFORM      ?= linux/arm64
DOCKER_MAKE   ?= docker/Makefile
DOCKER_IMAGE  ?= satellite1-deb-builder
DOCKER_TTY    ?= $(shell [ -t 1 ] && echo "-it")
DOCKER_RUN_FLAGS ?= --rm $(DOCKER_TTY)

OUT_DIR       ?= ${PWD}/build-assets
DEB_TARGET    := ${OUT_DIR}/$(PACKAGE_NAME)_$(SDK_VERSION)_$(ARCH).deb

BUILD_DIR     ?= ${PWD}/build/sdk
DEBIAN_DIR    := ${BUILD_DIR}/debian

LOCAL_VENV    ?= ${PWD}/.venv
PYTHON        ?= python3.11
VENV_PY       ?= $(LOCAL_VENV)/bin/python
VENV_PIP      ?= $(LOCAL_VENV)/bin/pip
PYTEST        ?= $(VENV_PY) -m pytest
RUFF          ?= $(LOCAL_VENV)/bin/ruff
MYPY          ?= $(LOCAL_VENV)/bin/mypy
PRECOMMIT     ?= $(LOCAL_VENV)/bin/pre-commit
DURATION      ?= 1
BOARD         ?= sq66
XMOS_FW_VERSION ?=
XMOS_FW_REPO ?=
XMOS_FW_ASSET ?=
XMOS_FW_BIN ?=
XMOS_FW_MD5 ?=
XMOS_FW_OUT_DIR ?=

# --- Metadata ---
PYPROJ_VERSION := $(shell $(PYTHON) -m setuptools_scm 2>/dev/null || echo unknown)
PYPROJ_RELEASE := $(shell $(PYTHON) -m setuptools_scm --strip-dev 2>/dev/null || echo unknown)

GIT_NAME := $(shell git config user.name)
GIT_EMAIL := $(shell git config user.email)

# --- check for uncomitted changes ---
.PHONY: verify-git-is-clean
verify-git-is-clean:
ifndef ALLOW_DIRTY
	@echo "Checking for uncomitted changes..."
	@if ! git diff --quiet --ignore-submodules --; then \
	  echo "ERROR: Working tree is dirty. Commit or stash changes first."; \
	  echo "       (override with ALLOW_DIRTY=1)"; \
	  exit 1; \
	fi
else
    @echo "Skipping clean-tree check (ALLOW_DIRTY=$(ALLOW_DIRTY))"
endif

.PHONY: print-meta
print-meta:
	@echo "PYPROJ_VERSION=$(PYPROJ_VERSION)"
	@echo "GIT_NAME=$(GIT_NAME)"
	@echo "GIT_EMAIL=$(GIT_EMAIL)"

.PHONY: all shell deb docker-image clean help venv dev-install test test-file test-k lint typecheck precommit check sq66-test deploy-temp verify-temp deploy-deb deploy-xmos-firmware-deb xmos-firmware-fetch xmos-firmware-deb-from-gh deploy-xmos-firmware-deb-from-gh sq66-deploy-temp sq66-deploy-deb sq66-verify-temp hil-audio prep-deb-tree

help:
	@echo "General targets (device-agnostic):"
	@echo "  make build [ALLOW_DIRTY=1]            Build wheel artifacts into build-assets/"
	@echo "  make venv                              Create local development venv"
	@echo "  make dev-install                       Install package with dev extras into .venv"
	@echo "  make test                              Run full pytest suite with repo venv"
	@echo "  make test-file FILE=tests/test_x.py    Run one pytest module"
	@echo "  make test-k K='expr'                   Run pytest with -k expression"
	@echo "  make lint                              Run ruff checks on src/ and tests/"
	@echo "  make typecheck                         Run mypy for src/"
	@echo "  make precommit                         Run pre-commit hooks on all files"
	@echo "  make check                             Run lint + typecheck + test"
	@echo "  make deploy-temp [HOST=user@ip]        Dev/debug temp wheel deploy to Pi"
	@echo "  make verify-temp [HOST=user@ip]        Verify temp deploy on Pi (set BOARD=...)"
	@echo "  make deploy-deb [HOST=user@ip]         Build .deb and install on Pi over SSH"
	@echo "  make deploy-xmos-firmware-deb [HOST=user@ip]  Build XMOS firmware .deb and install"
	@echo "  make xmos-firmware-fetch XMOS_FW_VERSION=vX.Y.Z    Download and verify XMOS firmware zip"
	@echo "  make xmos-firmware-deb-from-gh XMOS_FW_VERSION=vX.Y.Z   Download firmware and build .deb"
	@echo "  make deploy-xmos-firmware-deb-from-gh HOST=user@ip XMOS_FW_VERSION=vX.Y.Z"
	@echo "  make hil-audio [DURATION=1]            Run on-device ALSA capture HIL checks"
	@echo "  note: HOST defaults from .env via SAT1_HOST"
	@echo "  note: XMOS firmware defaults can come from .env (XMOS_FW_REPO, XMOS_FW_ASSET, XMOS_FW_BIN, XMOS_FW_MD5, XMOS_FW_OUT_DIR)"
	@echo
	@echo "SQ66 targets:"
	@echo "  make sq66-test                         Run SQ66-focused pytest selection"
	@echo "  make sq66-deploy-temp [HOST=user@ip]   Alias of deploy-temp"
	@echo "  make sq66-verify-temp [HOST=user@ip]   Verify temp deploy on Pi with BOARD=sq66"
	@echo "  make sq66-deploy-deb [HOST=user@ip]    Alias of deploy-deb"
	@echo "  note: sq66 targets fall back to SQ66_HOST, then SAT1_HOST"

all: $(DEB_TARGET) build

deb: $(DEB_TARGET)

docker-image:
	$(MAKE) -C ./docker deb-image

build: verify-git-is-clean | $(OUT_DIR)
	$(DOCKER) run $(DOCKER_RUN_FLAGS) \
		-v "${PWD}":/work \
		-v "${OUT_DIR}":/out \
		$(DOCKER_IMAGE) \
		/usr/bin/python3.11 -m build --outdir /out

$(OUT_DIR):
	@echo "Creating $(OUT_DIR)"
	mkdir -p "$(OUT_DIR)"
	echo "*" > "$(OUT_DIR)/.gitignore"

# build the wheel file and wrap it into a .deb package
$(DEB_TARGET): docker-image verify-git-is-clean prep-deb-tree | $(OUT_DIR)
	mkdir -p "$(OUT_DIR)"
	$(DOCKER) run --rm --platform=$(PLATFORM) \
	  -v "$(BUILD_DIR)":/work/src \
	  -v "$(OUT_DIR)":/out \
	  -v "${PWD}":/project \
	  -w /work/src \
	  $(DOCKER_IMAGE) \
	  bash -lc ' \
	  	dpkg-buildpackage -b -us -uc && \
		cp ../*.deb debian/.wheelhouse/satellite1*.whl /out'
	@echo
	@echo "Built package: $(DEB_TARGET)"

prep-deb-tree: | $(BUILD_DIR)
	rm -rf "$(DEBIAN_DIR)" "$(BUILD_DIR)/etc"
	cp -r "debian" "$(BUILD_DIR)"
	cp -r "etc" "$(BUILD_DIR)"

$(BUILD_DIR):
	@echo "Creating $(BUILD_DIR)"
	mkdir -p "$(BUILD_DIR)"
	echo "*" > "$(BUILD_DIR)/.gitignore"





$(LOCAL_VENV):
	$(PYTHON) -m venv $(LOCAL_VENV)
	$(LOCAL_VENV)/bin/pip install --upgrade pip
	$(LOCAL_VENV)/bin/pip install -e .


venv:
	@test -x "$(VENV_PY)" || ( \
	  command -v "$(PYTHON)" >/dev/null 2>&1 || { echo "ERROR: $(PYTHON) not found"; exit 10; }; \
	  "$(PYTHON)" -m venv "$(LOCAL_VENV)"; \
	)
	@"$(VENV_PIP)" install --upgrade pip


dev-install: venv
	@"$(VENV_PIP)" install -e .[dev]


test: dev-install
	@$(PYTEST)


test-file: dev-install
	@test -n "$(FILE)" || { echo "Usage: make test-file FILE=tests/test_x.py"; exit 2; }
	@$(PYTEST) "$(FILE)" -q


test-k: dev-install
	@test -n "$(K)" || { echo "Usage: make test-k K='sq66 or board_selection'"; exit 2; }
	@$(PYTEST) -k "$(K)" -q


lint: dev-install
	@"$(RUFF)" check src tests


typecheck: dev-install
	@"$(MYPY)" --config-file=pyproject.toml src


precommit: dev-install
	@"$(PRECOMMIT)" run --all-files


check: lint typecheck test


sq66-test: dev-install
	@$(PYTEST) -k "sq66 or board_selection or cli_dac" -q


deploy-temp:
	@test -n "$(HOST)" || { echo "Usage: make deploy-temp HOST=user@ip [WHEEL=path/to/package.whl] [SKIP_BUILD=1]"; exit 10; }
	@./scripts/deploy_temp_sdk.sh --host "$(HOST)" $(if $(WHEEL),--wheel "$(WHEEL)") $(if $(filter 1,$(SKIP_BUILD)),--skip-build)


sq66-deploy-temp:
	@SQ66_HOST_VALUE="$(or $(HOST),$(SQ66_HOST),$(SAT1_HOST))"; \
	  test -n "$$SQ66_HOST_VALUE" || { echo "Usage: make sq66-deploy-temp HOST=user@ip [WHEEL=path/to/package.whl] [SKIP_BUILD=1] (or set SQ66_HOST/SAT1_HOST in .env)"; exit 10; }; \
	  ./scripts/deploy_temp_sdk.sh --host "$$SQ66_HOST_VALUE" $(if $(WHEEL),--wheel "$(WHEEL)") $(if $(filter 1,$(SKIP_BUILD)),--skip-build)


deploy-deb:
	@test -n "$(HOST)" || { echo "Usage: make deploy-deb HOST=user@ip [DEB=path/to/package.deb] [SKIP_BUILD=1]"; exit 10; }
	@./scripts/deploy_deb_package.sh --host "$(HOST)" --package satellite1-rpi-sdk --make-target deb --deb-glob 'satellite1-rpi-sdk_*.deb' $(if $(DEB),--deb "$(DEB)") $(if $(filter 1,$(SKIP_BUILD)),--skip-build)


deploy-xmos-firmware-deb:
	@test -n "$(HOST)" || { echo "Usage: make deploy-xmos-firmware-deb HOST=user@ip [DEB=path/to/package.deb] [SKIP_BUILD=1]"; exit 10; }
	@./scripts/deploy_deb_package.sh --host "$(HOST)" --package satellite1-xmos-firmware --make-target xmos-firmware-deb --deb-glob 'satellite1-xmos-firmware_*.deb' $(if $(DEB),--deb "$(DEB)") $(if $(filter 1,$(SKIP_BUILD)),--skip-build)


xmos-firmware-fetch:
	@test -n "$(XMOS_FW_VERSION)" || { echo "Usage: make xmos-firmware-fetch XMOS_FW_VERSION=vX.Y.Z"; exit 10; }
	@FETCH_RESULT="$$(./scripts/fetch_xmos_firmware.sh --version "$(XMOS_FW_VERSION)" $(if $(XMOS_FW_REPO),--repo "$(XMOS_FW_REPO)") $(if $(XMOS_FW_ASSET),--asset "$(XMOS_FW_ASSET)") $(if $(XMOS_FW_BIN),--firmware-bin "$(XMOS_FW_BIN)") $(if $(XMOS_FW_MD5),--md5-file "$(XMOS_FW_MD5)") $(if $(XMOS_FW_OUT_DIR),--out-dir "$(XMOS_FW_OUT_DIR)"))" && \
	  echo "Fetched firmware: $${FETCH_RESULT%%|*}" && \
	  echo "Normalized version: $${FETCH_RESULT##*|}"


xmos-firmware-deb-from-gh:
	@test -n "$(XMOS_FW_VERSION)" || { echo "Usage: make xmos-firmware-deb-from-gh XMOS_FW_VERSION=vX.Y.Z"; exit 10; }
	@FETCH_RESULT="$$(./scripts/fetch_xmos_firmware.sh --version "$(XMOS_FW_VERSION)" $(if $(XMOS_FW_REPO),--repo "$(XMOS_FW_REPO)") $(if $(XMOS_FW_ASSET),--asset "$(XMOS_FW_ASSET)") $(if $(XMOS_FW_BIN),--firmware-bin "$(XMOS_FW_BIN)") $(if $(XMOS_FW_MD5),--md5-file "$(XMOS_FW_MD5)") $(if $(XMOS_FW_OUT_DIR),--out-dir "$(XMOS_FW_OUT_DIR)"))" && \
	  FW_BIN="$${FETCH_RESULT%%|*}" && \
	  FW_VER="$${FETCH_RESULT##*|}" && \
	  $(MAKE) xmos-firmware-deb FIRMWARE_BIN="$$FW_BIN" FIRMWARE_VERSION="$$FW_VER" OUT_DIR="$(OUT_DIR)"


deploy-xmos-firmware-deb-from-gh:
	@test -n "$(HOST)" || { echo "Usage: make deploy-xmos-firmware-deb-from-gh HOST=user@ip XMOS_FW_VERSION=vX.Y.Z"; exit 10; }
	@test -n "$(XMOS_FW_VERSION)" || { echo "Usage: make deploy-xmos-firmware-deb-from-gh HOST=user@ip XMOS_FW_VERSION=vX.Y.Z"; exit 10; }
	@FETCH_RESULT="$$(./scripts/fetch_xmos_firmware.sh --version "$(XMOS_FW_VERSION)" $(if $(XMOS_FW_REPO),--repo "$(XMOS_FW_REPO)") $(if $(XMOS_FW_ASSET),--asset "$(XMOS_FW_ASSET)") $(if $(XMOS_FW_BIN),--firmware-bin "$(XMOS_FW_BIN)") $(if $(XMOS_FW_MD5),--md5-file "$(XMOS_FW_MD5)") $(if $(XMOS_FW_OUT_DIR),--out-dir "$(XMOS_FW_OUT_DIR)"))" && \
	  FW_BIN="$${FETCH_RESULT%%|*}" && \
	  FW_VER="$${FETCH_RESULT##*|}" && \
	  $(MAKE) xmos-firmware-deb FIRMWARE_BIN="$$FW_BIN" FIRMWARE_VERSION="$$FW_VER" OUT_DIR="$(OUT_DIR)" && \
	  $(MAKE) deploy-xmos-firmware-deb HOST="$(HOST)" SKIP_BUILD=1


sq66-deploy-deb:
	@SQ66_HOST_VALUE="$(or $(HOST),$(SQ66_HOST),$(SAT1_HOST))"; \
	  test -n "$$SQ66_HOST_VALUE" || { echo "Usage: make sq66-deploy-deb HOST=user@ip [DEB=path/to/package.deb] [SKIP_BUILD=1] (or set SQ66_HOST/SAT1_HOST in .env)"; exit 10; }; \
	  ./scripts/deploy_deb_package.sh --host "$$SQ66_HOST_VALUE" --package satellite1-rpi-sdk --make-target deb --deb-glob 'satellite1-rpi-sdk_*.deb' $(if $(DEB),--deb "$(DEB)") $(if $(filter 1,$(SKIP_BUILD)),--skip-build)


verify-temp:
	@test -n "$(HOST)" || { echo "Usage: make verify-temp HOST=user@ip [BOARD=sq66] [RUN_DAC_SETUP=1]"; exit 10; }
	@./scripts/deploy_temp_verify.sh --host "$(HOST)" --board "$(BOARD)" $(if $(filter 1,$(RUN_DAC_SETUP)),--run-dac-setup)


sq66-verify-temp:
	@SQ66_HOST_VALUE="$(or $(HOST),$(SQ66_HOST),$(SAT1_HOST))"; \
	  test -n "$$SQ66_HOST_VALUE" || { echo "Usage: make sq66-verify-temp HOST=user@ip [RUN_DAC_SETUP=1] (or set SQ66_HOST/SAT1_HOST in .env)"; exit 10; }; \
	  ./scripts/deploy_temp_verify.sh --host "$$SQ66_HOST_VALUE" --board sq66 $(if $(filter 1,$(RUN_DAC_SETUP)),--run-dac-setup)


hil-audio:
	@./scripts/hil_audio.sh --duration "$(DURATION)"


.PHONY: kernel-pkg
kernel-pkg: $(OUR_DIR)
	$(MAKE) -C ./sys-packages/rpi-kernel-fusb302 deb OUT_DIR="$(OUT_DIR)"

.PHONY: rpi-setup-deb
rpi-setup-deb: $(OUT_DIR)
	$(MAKE) -C ./sys-packages/satellite1-rpi-setup deb OUT_DIR="$(OUT_DIR)"

.PHONY: xmos-firmware-deb
xmos-firmware-deb: $(OUT_DIR)
	$(MAKE) -C ./sys-packages/satellite1-xmos-firmware deb OUT_DIR="$(OUT_DIR)"

clean:
	rm -rf "$(BUILD_DIR)" "$(DEB_TARGET)"

shell: docker-image
	$(DOCKER) run $(DOCKER_RUN_FLAGS) \
		-v "${PWD}":/work \
		-e "EDITOR=/usr/bin/vim" \
		-e "DEBEMAIL=$(GIT_EMAIL)" \
		-e "DEBFULLNAME=$(GIT_NAME)" \
		-e "PRJ_VER=$(PYPROJ_RELEASE)" \
		$(DOCKER_IMAGE) \
		/bin/bash
