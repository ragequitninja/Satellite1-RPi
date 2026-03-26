from satellite1.components import dac3101 as dac_mod


class FakeI2c:
    writes: list[tuple[int, int]] = []

    def __init__(self, bus: int, addr: int):
        self.bus = bus
        self.addr = addr

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def write_byte(self, register: int, value: int) -> None:
        self.writes.append((register, value))

    def read_byte(self, register: int) -> int:
        return 0


def test_dac3101_setup_writes_reset_and_unmute(monkeypatch):
    FakeI2c.writes = []
    monkeypatch.setattr(dac_mod, "I2cInterface", FakeI2c)

    dac = dac_mod.DAC3101(
        dac_mod.DAC3101Config(i2c_bus=1, i2c_addr=0x18, volume=0.5, muted=False)
    )
    dac.setup()

    assert (dac_mod.DAC3101.REG_SW_RST, 0x01) in FakeI2c.writes
    assert (dac_mod.DAC3101.REG_DAC_VOL, 0x00) in FakeI2c.writes


def test_dac3101_mute_and_volume(monkeypatch):
    FakeI2c.writes = []
    monkeypatch.setattr(dac_mod, "I2cInterface", FakeI2c)

    dac = dac_mod.DAC3101(
        dac_mod.DAC3101Config(i2c_bus=1, i2c_addr=0x18, volume=0.5, muted=False)
    )
    assert dac.set_mute_on() is True
    assert (dac_mod.DAC3101.REG_DAC_VOL, 0x0C) in FakeI2c.writes

    FakeI2c.writes = []
    assert dac.set_volume(1.0) is True
    assert (dac_mod.DAC3101.REG_DACL_VOL_D, 0x00) in FakeI2c.writes
