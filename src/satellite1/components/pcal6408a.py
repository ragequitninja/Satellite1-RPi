from __future__ import annotations

import logging
import time

from pydantic import BaseModel, Field

from ..hal.i2c_interface import I2cInterface

log = logging.getLogger(__name__)


class PCAL6408AConfig(BaseModel):
    enabled: bool = True
    i2c_bus: int = Field(1, ge=0)
    i2c_addr: int = Field(0x20, ge=0x00, le=0x7F)


class PCAL6408A:
    REG_INPUT_PORT = 0x00
    REG_OUTPUT_PORT = 0x01
    REG_CONFIGURATION = 0x03
    REG_INTERRUPT_MASK = 0x45

    XVF_RST_N_PIN = 0
    INT_N_PIN = 1
    DAC_RST_N_PIN = 2
    BOOT_SEL_PIN = 3
    MCLK_OE_PIN = 4
    SPI_OE_PIN = 5
    I2S_OE_PIN = 6
    MUTE_PIN = 7

    def __init__(self, config: PCAL6408AConfig) -> None:
        self.config = config
        self._i2c = I2cInterface(config.i2c_bus, config.i2c_addr)

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def setup(self) -> None:
        if not self.enabled:
            return

        with self._i2c as bus:
            out_hold_dac_reset = (
                (1 << self.XVF_RST_N_PIN)
                | (1 << self.INT_N_PIN)
                | (1 << self.BOOT_SEL_PIN)
                | (1 << self.MCLK_OE_PIN)
                | (1 << self.SPI_OE_PIN)
                | (1 << self.I2S_OE_PIN)
                | (1 << self.MUTE_PIN)
            )
            bus.write_byte(self.REG_OUTPUT_PORT, out_hold_dac_reset)
            time.sleep(0.1)

            conf = (
                (1 << self.XVF_RST_N_PIN)
                | (1 << self.INT_N_PIN)
                | (1 << self.BOOT_SEL_PIN)
                | (1 << self.MUTE_PIN)
            )
            bus.write_byte(self.REG_CONFIGURATION, conf)
            time.sleep(0.1)

            int_mask = 0xFF & ~(1 << self.INT_N_PIN)
            bus.write_byte(self.REG_INTERRUPT_MASK, int_mask)
            time.sleep(0.1)

            out_release_dac_reset = out_hold_dac_reset | (1 << self.DAC_RST_N_PIN)
            bus.write_byte(self.REG_OUTPUT_PORT, out_release_dac_reset)

            inp = bus.read_byte(self.REG_INPUT_PORT)
            log.info(
                "PCAL6408A setup done. INPUT=0x%02X OUT=0x%02X CONF=0x%02X MASK=0x%02X",
                inp,
                out_release_dac_reset,
                conf,
                int_mask,
            )
