from __future__ import annotations

import logging
import time

from pydantic import BaseModel, Field

from ..hal.i2c_interface import I2cInterface

log = logging.getLogger(__name__)


class DAC3101Config(BaseModel):
    enabled: bool = True
    i2c_bus: int = Field(1, ge=0)
    i2c_addr: int = Field(0x18, ge=0x00, le=0x7F)
    volume: float = Field(0.7, ge=0.0, le=1.0)
    muted: bool = False


class DAC3101:
    REG_PAGE_CTRL = 0x00
    REG_SW_RST = 0x01
    REG_CLK_GEN_MUX = 0x04
    REG_PLL_P_R = 0x05
    REG_PLL_J = 0x06
    REG_PLL_D_MSB = 0x07
    REG_PLL_D_LSB = 0x08
    REG_NDAC_VAL = 0x0B
    REG_MDAC_VAL = 0x0C
    REG_DOSR_VAL_MSB = 0x0D
    REG_DOSR_VAL_LSB = 0x0E
    REG_CLKOUT_MUX = 0x19
    REG_CLKOUT_M_VAL = 0x1A
    REG_CODEC_IF = 0x1B
    REG_B_DIV_VAL = 0x1E
    REG_GPIO1_IO = 0x33
    REG_DAC_DAT_PATH = 0x3F
    REG_DAC_VOL = 0x40
    REG_DACL_VOL_D = 0x41
    REG_DACR_VOL_D = 0x42

    REG_HP_DRVR = 0x1F
    REG_SPK_AMP = 0x20
    REG_HP_DEPOP = 0x21
    REG_DAC_OP_MIX = 0x23
    REG_HPL_VOL_A = 0x24
    REG_HPR_VOL_A = 0x25
    REG_SPKL_VOL_A = 0x26
    REG_SPKR_VOL_A = 0x27
    REG_HPL_DRVR = 0x28
    REG_HPR_DRVR = 0x29
    REG_SPKL_DRVR = 0x2A
    REG_SPKR_DRVR = 0x2B

    def __init__(self, config: DAC3101Config):
        self.config = config
        self._i2c = I2cInterface(config.i2c_bus, config.i2c_addr)
        self._muted = config.muted
        self._volume = config.volume

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def volume(self) -> float:
        return self._volume

    def _wr(self, bus: I2cInterface, reg: int, value: int) -> None:
        bus.write_byte(reg, value & 0xFF)

    def _set_page(self, bus: I2cInterface, page: int) -> None:
        self._wr(bus, self.REG_PAGE_CTRL, page)

    def setup(self) -> None:
        if not self.enabled:
            return

        pll_j = 0x08
        pll_d = 0x000
        pll_p = 0x01
        pll_r = 0x01
        ndac = 0x02
        mdac = 0x01
        dosr = 256
        b_div = 0x01

        with self._i2c as bus:
            self._set_page(bus, 0x00)
            self._wr(bus, self.REG_SW_RST, 0x01)
            time.sleep(0.1)

            self._wr(bus, self.REG_PLL_J, pll_j)
            self._wr(bus, self.REG_PLL_D_LSB, (pll_d >> 0) & 0xFF)
            self._wr(bus, self.REG_PLL_D_MSB, (pll_d >> 8) & 0xFF)
            self._wr(bus, self.REG_B_DIV_VAL, 0x80 | (b_div & 0x7F))
            time.sleep(0.1)

            self._wr(bus, self.REG_CLK_GEN_MUX, 0x07)
            self._wr(
                bus, self.REG_PLL_P_R, 0x80 | ((pll_p & 0x0F) << 4) | (pll_r & 0x0F)
            )
            self._wr(bus, self.REG_NDAC_VAL, 0x80 | (ndac & 0x7F))
            self._wr(bus, self.REG_MDAC_VAL, 0x80 | (mdac & 0x7F))

            self._wr(bus, self.REG_DOSR_VAL_LSB, dosr & 0xFF)
            self._wr(bus, self.REG_DOSR_VAL_MSB, (dosr >> 8) & 0xFF)

            self._wr(bus, self.REG_CLKOUT_MUX, 0x04)
            self._wr(bus, self.REG_CLKOUT_M_VAL, 0x80 | 0x01)
            self._wr(bus, self.REG_GPIO1_IO, 0x10)
            self._wr(bus, self.REG_CODEC_IF, 0x30)

            self._set_page(bus, 0x01)
            self._wr(bus, self.REG_HP_DRVR, 0x14)
            self._wr(bus, self.REG_HP_DEPOP, 0x4E)
            self._wr(bus, self.REG_DAC_OP_MIX, 0x44)

            self._wr(bus, self.REG_HPL_DRVR, 0x06)
            self._wr(bus, self.REG_HPR_DRVR, 0x06)
            self._wr(bus, self.REG_SPKL_DRVR, 0x0C)
            self._wr(bus, self.REG_SPKR_DRVR, 0x0C)

            self._wr(bus, self.REG_HP_DRVR, 0xD4)
            self._wr(bus, self.REG_SPK_AMP, 0xC6)

            for reg in (
                self.REG_HPL_VOL_A,
                self.REG_HPR_VOL_A,
                self.REG_SPKL_VOL_A,
                self.REG_SPKR_VOL_A,
            ):
                self._wr(bus, reg, 0x92)

            time.sleep(0.1)

            self._set_page(bus, 0x00)
            self._wr(bus, self.REG_DAC_DAT_PATH, 0xD4)
            self._wr(bus, self.REG_DACL_VOL_D, 0x00)
            self._wr(bus, self.REG_DACR_VOL_D, 0x00)
            self._wr(bus, self.REG_DAC_VOL, 0x00)
            time.sleep(0.1)

        self._write_volume()
        self._write_mute()
        log.info("DAC3101 setup complete.")

    def set_mute_on(self) -> bool:
        self._muted = True
        return self._write_mute()

    def set_mute_off(self) -> bool:
        self._muted = False
        return self._write_mute()

    def is_muted(self) -> bool:
        return self._muted

    def set_volume(self, volume: float) -> bool:
        self._volume = max(0.0, min(1.0, float(volume)))
        return self._write_volume()

    def _write_volume(self) -> bool:
        code = int(round((1.0 - self._volume) * 127.0))
        code = max(0, min(127, code))
        try:
            with self._i2c as bus:
                self._set_page(bus, 0x00)
                self._wr(bus, self.REG_DACL_VOL_D, code)
                self._wr(bus, self.REG_DACR_VOL_D, code)
            return True
        except OSError as e:
            log.error("Writing volume failed: %s", e)
            return False

    def _write_mute(self) -> bool:
        try:
            with self._i2c as bus:
                self._set_page(bus, 0x00)
                self._wr(bus, self.REG_DAC_VOL, 0x0C if self._muted else 0x00)
            return True
        except OSError as e:
            log.error("Writing mute failed: %s", e)
            return False
