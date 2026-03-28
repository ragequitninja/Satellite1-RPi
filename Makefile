PACKAGE_NAME  ?= satellite1-rpi-sdk
SDK_VERSION   ?= 1.0
ARCH          ?= arm64

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

.PHONY: all shell deb docker-image clean help venv dev-install test test-file test-k lint typecheck precommit check sq66-test sq66-deploy-temp sq66-verify-temp hil-audio

help:
	@echo "Common targets:"
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
	@echo "  make sq66-test                         Run SQ66-focused pytest selection"
	@echo "  make sq66-deploy-temp HOST=user@ip     Dev/debug temp wheel deploy to Pi"
	@echo "  make sq66-verify-temp HOST=user@ip     Verify temp deploy on Pi"
	@echo "  make hil-audio [DURATION=1]            Run on-device ALSA capture HIL checks"

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
$(DEB_TARGET): docker-image verify-git-is-clean $(DEBIAN_DIR) | $(OUT_DIR)
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

$(DEBIAN_DIR):
	@echo "Creating $(BUILD_DIR)"
	mkdir -p "$(BUILD_DIR)"
	echo "*" > "$(BUILD_DIR)/.gitignore"
	cp -r "debian" "$(BUILD_DIR)"
	cp -r "etc" "$(BUILD_DIR)"



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


sq66-deploy-temp:
	@test -n "$(HOST)" || { echo "Usage: make sq66-deploy-temp HOST=user@ip"; exit 10; }
	@./scripts/deploy_temp_sdk.sh --host "$(HOST)"


sq66-verify-temp:
	@test -n "$(HOST)" || { echo "Usage: make sq66-verify-temp HOST=user@ip"; exit 10; }
	@./scripts/deploy_temp_verify.sh --host "$(HOST)" --board sq66


hil-audio:
	@./scripts/hil_audio.sh --duration "$(DURATION)"


.PHONY: kernel-pkg
kernel-pkg: $(OUR_DIR)
	$(MAKE) -C ./sys-packages/rpi-kernel-fusb302 deb OUT_DIR="$(OUT_DIR)"

.PHONY: rpi-setup-deb
rpi-setup-deb: $(OUT_DIR)
	$(MAKE) -C ./sys-packages/satellite1-rpi-setup deb OUT_DIR="$(OUT_DIR)"

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
