# 🚧 Experimental repository
> **Early-stage development only.**
> **No support is provided yet. Use at your own risk.**
---
## Satellite1-RPi

**Raspberry Pi SDK for the Satellite1-HAT**

This repository contains all components required to run the Satellite1-HAT on a Raspberry Pi Zero W2:

- **`satellite1-rpi`** — Python SDK library
- **`satellite1-rpi-setup`** — Raspberry Pi configuration packaged as a `.deb`
- **`rpi-kernel-fusb302`** — Custom Raspberry Pi kernel with USB-C Power Delivery support
- **`image-builder`** — Generates SD-card images with everything preinstalled

> **Target Platform:** Raspberry Pi Zero W2
> **OS:** Raspberry Pi OS (Bookworm)

---

## Table of contents
- [Quick start](#quick-start)
- [RPi Setup](#rpi-setup)
- [CLI Usage](#cli-usage)
- [Development](#development)

---

## Quick start

### Flash the Satellite1 SDK Image
The easiest way to set up the Satellite1-HAT is to flash the prepared **Satellite1 SDK Image**.
This image includes:

- Raspberry Pi OS (Bookworm)
- Custom kernel with FUSB302 USB-C PD support
- All necessary overlays and configuration
- The Satellite1 Python SDK + CLI
- Automatic DAC initialization at boot

**Steps:**

1. Install **Raspberry Pi Imager**
2. In *Application Settings*, set:
   **Content Repository → `<your repository URL>`**
3. Select the **Satellite1 SDK Image**
4. Flash it to an SD card
5. Boot the Raspberry Pi Zero W2 with the Satellite1-HAT installed

---

## RPi Setup

### 1. Kernel with USB-C Power Delivery Support

The default kernel shipped with Raspberry Pi OS does **not** include support for USB-C Power Delivery.

Install the custom kernel:

```bash
sudo dpkg -i linux-image-6.12.58-fusb302-rpi-v8_2_arm64.deb
```

This kernel includes:

```
CONFIG_TYPEC=m
CONFIG_TYPEC_TCPM=m
CONFIG_TYPEC_TCPCI=m
CONFIG_TYPEC_FUSB302=m
```

Reboot after installation.

---

### 2. Device Tree Overlays and Module Configuration

Install the setup package:

```bash
sudo dpkg -i satellite1-rpi-setup_1.0-1_arm64.deb
```

Installs and configures:

- FUSB302 overlay (USB-C PD)
- Satellite1 I²S audio overlay
- `/etc/alsa/conf.d/50-satellite1.conf`
- Loads `i2c-dev` on startup
- Enables SPI, I²S, and I2C in `/boot/firmware/config.txt`
- Adds sensor overlay:
  `i2c-sensor,addr=0x38,chip=aht20`

#### ALSA capture behavior

The XMOS capture stream is physically clocked at 48 kHz, but microphone content is effectively
16 kHz bandwidth. The setup package configures ALSA as follows:

- `default` capture path (`satellite1_capture`) is fixed to 16 kHz.
- `satellite1_capture_raw48` is available for diagnostics/scripts that need the raw 48 kHz stream.

Examples:

```bash
# Recommended capture path for normal applications
arecord -D default -r 16000 -f S32_LE -c 2 out_16k.wav

# Raw 48 kHz path for custom unpacking/analysis
arecord -D satellite1_capture_raw48 -r 48000 -f S32_LE -c 2 out_raw48.wav
```

---

### 3. Python Satellite1 SDK

```bash
sudo dpkg -i satellite1-rpi-sdk_0.1.5_arm64.deb
```

This will:

- Create a venv at `/opt/satellite1/venv`
- Install the Satellite1 Python library
- Install the `sat1` CLI in `/usr/bin/sat1`
- Install `satellite1-init.service` (initializes DACs at boot)

---

## CLI Usage

The `sat1` CLI provides control over:

- DAC
- XMOS
- USB-C PD

---

### Global Usage

```bash
sat1 [-h] [--config CONFIG] [--board {satellite1,sq66}] [-v] {dac,xmos,pd} ...
```

#### Components

| Component | Description |
|----------|-------------|
| `dac`    | DAC audio controls |
| `xmos`   | XMOS interface and firmware controls |
| `pd`     | USB-C PD contract status |

#### Options

| Option | Description |
|--------|-------------|
| `-h`, `--help` | Show help |
| `--config FILE` | Custom TOML config (default `/etc/satellite1.conf`) |
| `--board {satellite1,sq66}` | Select hardware profile |
| `-v`, `--verbose` | Increase verbosity |

### SQ66 Debug Board

The SQ66 board is supported as a debug/testing target.

- Select it with `--board sq66` (or env `SAT1_BOARD=sq66`)
- It is line-out only; speaker DAC commands are not available

Examples:

```bash
sat1 --board sq66 dac setup
sat1 --board sq66 dac volume
```

---

## DAC Controls

```bash
sat1 dac [options] {volume,set-volume,mute,unmute,setup,plugged-in,status}
```

### Commands

| Command | Description |
|---------|-------------|
| `volume` | Read current volume |
| `set-volume` | Set volume |
| `mute` | Mute line-out |
| `unmute` | Unmute line-out |
| `setup` | Initialize DAC |
| `plugged-in` | Detect headphone jack |
| `status` | Show status |

---

### DAC Selection

```bash
--dac {auto,line-out,speaker}
```

---

### Line-Out Overrides

| Option | Description |
|--------|-------------|
| `--line-out-enabled` / `--no-line-out-enabled` | Enable/disable line-out |
| `--line-out-startup-volume <0..1>` | Initial volume |
| `--line-out-startup-muted` / `--no-line-out-startup-muted` | Mute at startup |
| `--line-out-restore-on-startup` / `--no-line-out-restore-on-startup` | Restore previous state |

---

### Speaker Overrides

| Option | Description |
|--------|-------------|
| `--speaker-enabled` / `--no-speaker-enabled` | Enable/disable speaker |
| `--speaker-startup-volume <0..1>` | Startup volume |
| `--speaker-startup-muted` / `--no-speaker-startup-muted` | Mute at startup |
| `--speaker-restore-on-startup` / `--no-speaker-restore-on-startup` | Restore previous state |
| `--speaker-channel {left,right,dwn_mix}` | Output routing |
| `--speaker-amp-level <int>` | Amplifier gain |

---

## XMOS Controls

```bash
sat1 xmos {setup,read-firmware,read-status,reset,enable-flashing,disable-flashing,run-spi-test,set-mic-output,flash-firmware}
```

### Commands

| Command | Description |
|---------|-------------|
| `setup` | Initialize SPI/GPIO |
| `read-firmware` | Read firmware version |
| `read-status` | Read status register |
| `reset` | Toggle reset |
| `enable-flashing` | Enter flashing mode |
| `disable-flashing` | Exit flashing mode |
| `run-spi-test` | SPI echo test |
| `set-mic-output` | Configure I²S microphone routing |
| `flash-firmware` | Flash XMOS firmware |

---

## Power Delivery

```bash
sat1 pd
```

Shows current USB-C Power Delivery contract.

---

## Development

### Prerequisites

- Python 3.11+
- `pip` and `venv`

### Local setup

```bash
make venv
make dev-install
```

### Development checks

```bash
make test
make test-file FILE=tests/test_cli/test_cli_dac.py
make test-k K="sq66 or board_selection"
make sq66-test
make lint
make typecheck
make precommit
make check
```

For a full list of development and debug targets:

```bash
make help
```

### SQ66 temporary deploy (dev/debug)

```bash
make sq66-deploy-temp HOST="$SQ66_RPI_HOST"
make sq66-verify-temp HOST="$SQ66_RPI_HOST"
```
