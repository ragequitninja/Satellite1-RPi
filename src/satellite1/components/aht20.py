import time
from pathlib import Path


def find_aht20_hwmon_base() -> Path:
    for path in Path("/sys/class/hwmon").glob("hwmon*/name"):
        if path.read_text().strip() == "aht10":
            return path.parent
    raise RuntimeError("AHT hwmon device not found")


def read_temperature_humidity(base: Path | None = None) -> tuple[float, float]:
    hwmon_base = base or find_aht20_hwmon_base()
    temperature = int((hwmon_base / "temp1_input").read_text()) / 1000.0
    humidity = int((hwmon_base / "humidity1_input").read_text()) / 1000.0
    return temperature, humidity


def main(samples: int = 5, interval_s: float = 1.0) -> int:
    for _ in range(samples):
        temp_c, rh = read_temperature_humidity()
        print(f"T={temp_c:.3f} C  RH={rh:.3f} %")
        time.sleep(interval_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
