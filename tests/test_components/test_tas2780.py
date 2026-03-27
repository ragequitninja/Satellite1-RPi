from satellite1.components.tas2780 import dac as tas_mod


class FakeI2c:
    writes: list[tuple[int, int]] = []

    def __init__(self, bus: int, addr: int):
        self.bus = bus
        self.addr = addr

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def write_byte(self, register: int, value: int) -> None:
        self.writes.append((register, value))

    def read_byte(self, register: int) -> int:
        del register
        return 0


def _make_dac(channel: tas_mod.AudioCh) -> tas_mod.TAS2780:
    return tas_mod.TAS2780(
        tas_mod.TAS2780Config(i2c_bus=1, i2c_addr=0x3F, channel=channel)
    )


def test_write_channel_right_programs_mono_right(monkeypatch):
    FakeI2c.writes = []
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("right")
    dac._write_channel()

    cfg = tas_mod.REG.TDM_CFG2_RX_WLEN__32BIT | tas_mod.REG.TDM_CFG2_RX_SLEN__32BIT
    expected = tas_mod.REG.TDM_CFG2_RX_SCFG__MONO_RIGHT | cfg
    assert (tas_mod.REG.TDM_CFG2, expected) in FakeI2c.writes


def test_write_channel_downmix_programs_downmix(monkeypatch):
    FakeI2c.writes = []
    monkeypatch.setattr(tas_mod, "I2cInterface", FakeI2c)

    dac = _make_dac("dwn_mix")
    dac._write_channel()

    cfg = tas_mod.REG.TDM_CFG2_RX_WLEN__32BIT | tas_mod.REG.TDM_CFG2_RX_SLEN__32BIT
    expected = tas_mod.REG.TDM_CFG2_RX_SCFG__STEREO_DWN_MIX | cfg
    assert (tas_mod.REG.TDM_CFG2, expected) in FakeI2c.writes
