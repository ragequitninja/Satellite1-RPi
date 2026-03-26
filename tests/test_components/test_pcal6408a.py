from satellite1.components import pcal6408a as pcal_mod


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
        return 0xA5


def test_pcal6408a_setup_programs_expected_registers(monkeypatch):
    FakeI2c.writes = []
    monkeypatch.setattr(pcal_mod, "I2cInterface", FakeI2c)

    dev = pcal_mod.PCAL6408A(pcal_mod.PCAL6408AConfig(i2c_bus=1, i2c_addr=0x20))
    dev.setup()

    regs = [reg for reg, _ in FakeI2c.writes]
    assert regs == [
        pcal_mod.PCAL6408A.REG_OUTPUT_PORT,
        pcal_mod.PCAL6408A.REG_CONFIGURATION,
        pcal_mod.PCAL6408A.REG_INTERRUPT_MASK,
        pcal_mod.PCAL6408A.REG_OUTPUT_PORT,
    ]
