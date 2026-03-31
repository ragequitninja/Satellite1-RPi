# Import the module under test as "mod"
import importlib
import struct
import sys
import types

import pytest

MODULE_NAME = (
    "satellite1.components.xmos_device_cntrl"  # change if your filename differs
)


def load_module_with_stubbed_spidev():
    # Create a stub spidev module
    spidev_stub = types.SimpleNamespace()

    class SpiDevStub:
        def __init__(self):
            self.opened = False
            self.args = None
            self.max_speed_hz = None
            self.mode = None
            self.bits_per_word = None
            self.last_tx = None
            self._queue = []  # push responses here

        def open(self, bus, dev):
            self.opened = True
            self.args = (bus, dev)

        def xfer2(self, tx):
            self.last_tx = list(tx)
            if self._queue:
                return list(self._queue.pop(0))
            # default echo-ish: return header + zeros
            return [0, 0, 0] + [0] * (len(tx) - 3)

        def close(self):
            self.opened = False

        def queue(self, *responses):
            # push sequences to be returned on next xfer2 calls
            self._queue.extend(responses)

    spidev_stub.SpiDev = SpiDevStub

    # Inject stub into sys.modules BEFORE import
    sys.modules["spidev"] = spidev_stub

    if MODULE_NAME in sys.modules:
        del sys.modules[MODULE_NAME]
    return importlib.import_module(MODULE_NAME), spidev_stub


def test_open_close_sets_spi_and_config():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl(
        mod.DeviceCntrlConfig(
            bus=1, dev=2, max_speed_hz=1_000_000, mode=1, bits_per_word=8
        )
    )
    assert dev._spi is None
    dev.open()
    assert dev._spi is not None
    assert dev._spi.args == (1, 2)
    assert dev._spi.max_speed_hz == 1_000_000
    assert dev._spi.mode == 1
    assert dev._spi.bits_per_word == 8
    dev.close()
    assert dev._spi is None


def test_payload_slice_bug_is_fixed():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    # Queue a single non-ignored response (not RET_IGNORED_IN_DEVICE)
    dev._spi.queue([0x01, 0x00, 0x00, 0, 0, 0, 0])
    ok, data = dev.transfer(0x10, 0x00, b"\xaa\xbb\xcc", 0)
    assert ok and data is None  # write path
    dev.close()


def test_ignored_then_accepts():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    # First two rx: ignored, then accepted
    dev._spi.queue(
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0, 0],  # attempt 1
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0, 0],  # attempt 2
        [0x02, 0x00, 0x00, 0],  # accepted
    )
    ok, _ = dev.transfer(0x00, 0x00, b"", 0)
    assert ok is True
    dev.close()


def test_all_ignored_fails():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0],
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0],
        [mod.CntrlProto.RET_IGNORED_IN_DEVICE, 0, 0],
    )
    ok, data = dev.transfer(0x00, 0x00, b"", 0)
    assert ok is False and data is None
    dev.close()


def test_no_response_header_sums_to_zero_is_failure():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue([0, 0, 0] + [0] * 10)
    ok, data = dev.transfer(0x01, 0x00, b"", 0)
    assert ok is False and data is None
    dev.close()


def test_status_register_update_when_control_resource_id():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl(mod.DeviceCntrlConfig(status_reg_len=4))
    dev.open()
    # CNTRL_RES_ID with some status bytes
    dev._spi.queue([mod.CntrlProto.CNTRL_RES_ID, 0x00, 0x11, 0x22, 0x33, 0x44])
    ok, _ = dev.transfer(0x10, 0x00, b"\x01", 0)
    assert ok
    # Only the first 4 bytes should be captured into status buffer
    assert bytes(dev.dc_status_register_)[:4] == b"\x11\x22\x33\x44"
    dev.close()


def test_read_command_second_phase_returns_payload():
    mod, spidev_stub = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    # Phase 1 accepted
    dev._spi.queue([0x02, 0x00, 0x00])
    # Phase 2: payload available, data in rx2[1:1+len]
    payload = b"\xde\xad\xbe\xef\x01"
    rx2 = [mod.CntrlProto.RET_PAYLOAD_AVAILABLE] + list(payload) + [0, 0]
    dev._spi.queue(rx2)
    ok, data = dev.transfer(
        0xF0, 0x58 | mod.CntrlProto.CMD_READ_BIT, None, read_payload_len=len(payload)
    )
    assert ok and data == payload
    dev.close()


def test_read_command_accepts_legacy_dfu_payload_prefix_zero():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()

    payload = b"\x01\x00\x03\x04\x00"
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [0x00] + list(payload),
    )

    ok, data = dev.send_cmd(mod.DFU_SERVICER.CMD_GET_VERSION)
    assert ok and data == payload
    dev.close()


def test_read_command_accepts_legacy_audio_payload_prefix_zero():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()

    payload = bytes(range(1, 17))
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [0x00] + list(payload),
    )

    ok, data = dev.transfer(
        mod.AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
        mod.AUDIO_PIPELINE_CONTROL.CMD_GET_SETTINGS,
        None,
        read_payload_len=len(payload),
    )
    assert ok and data == payload
    dev.close()


def test_read_command_ignores_non_payload_frames_until_payload_available():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    # Phase 1 accepted
    dev._spi.queue([0x02, 0x00, 0x00])
    # second phase starts with non-payload header, then valid payload frame
    dev._spi.queue([0x01, 0x00, 0x11, 0x22, 0x33])
    payload = b"\xaa\xbb\xcc\xdd\xee"
    dev._spi.queue([mod.CntrlProto.RET_PAYLOAD_AVAILABLE] + list(payload))

    ok, data = dev.transfer(
        0xF0,
        0x58 | mod.CntrlProto.CMD_READ_BIT,
        None,
        read_payload_len=len(payload),
    )
    assert ok and data == payload
    dev.close()


def test_read_command_drains_stale_payload_before_issuing_new_read():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()

    stale = b"\x01\x02\x03\x04\x05"
    fresh = b"\x11\x22\x33\x44\x55"

    dev._may_have_stale_payload = True

    # Drain pass sees stale pending payload.
    dev._spi.queue([mod.CntrlProto.RET_PAYLOAD_AVAILABLE] + list(stale))
    # Second drain probe sees no pending payload and stops draining.
    dev._spi.queue([0x00, 0x00, 0x00])
    # Phase 1 command accepted.
    dev._spi.queue([0x02, 0x00, 0x00])
    # Phase 2 returns fresh payload.
    dev._spi.queue([mod.CntrlProto.RET_PAYLOAD_AVAILABLE] + list(fresh))

    ok, data = dev.transfer(
        0xF0,
        0x58 | mod.CntrlProto.CMD_READ_BIT,
        None,
        read_payload_len=len(fresh),
    )
    assert ok and data == fresh
    dev.close()


def test_read_command_retries_when_payload_frame_too_short():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()

    payload = b"\xaa\xbb\xcc\xdd\xee"

    # Phase 1 accepted
    dev._spi.queue([0x02, 0x00, 0x00])
    # First phase-2 frame is payload-available but too short.
    dev._spi.queue([mod.CntrlProto.RET_PAYLOAD_AVAILABLE, 0x99])
    # Next frame is valid and should be used.
    dev._spi.queue([mod.CntrlProto.RET_PAYLOAD_AVAILABLE] + list(payload))

    ok, data = dev.transfer(
        0xF0,
        0x58 | mod.CntrlProto.CMD_READ_BIT,
        None,
        read_payload_len=len(payload),
    )
    assert ok and data == payload
    dev.close()


def test_command_struct_validation():
    mod, _ = load_module_with_stubbed_spidev()
    with pytest.raises(ValueError):
        mod.DeviceCntrlCMD(-1, 0, 0)
    with pytest.raises(ValueError):
        mod.DeviceCntrlCMD(0, 256, 0)
    with pytest.raises(ValueError):
        mod.DeviceCntrlCMD(0, 0, mod.MAX_SPI_TRANSFER_LEN)  # too big


def test_status_dataclass_from_bytes():
    mod, _ = load_module_with_stubbed_spidev()
    sr = mod.DeviceCntrlStatusRegister.from_bytes(b"\x01\x02\x03\x04")
    assert (sr.device_status, sr.gpio_port_a, sr.gpio_port_b) == (1, 2, 3)


def test_encode_mic_output_partial_contains_expected_mask_and_padding():
    mod, _ = load_module_with_stubbed_spidev()
    payload = mod.XMOSDeviceCntrl.encode_mic_output_partial(
        i2s_channel_map=(1, 4),
        upsample_channel_map=(0, 1, 2, 3, 4, 5),
        pack_extra_upsample_channels=True,
    )
    assert len(payload) == 16
    field_mask = int.from_bytes(payload[:4], "little")
    assert field_mask == 0x1C
    assert payload[4:13] == bytes([1, 1, 4, 0, 1, 2, 3, 4, 5])
    assert payload[13:16] == b"\x00\x00\x00"


def test_decode_mic_output_settings_round_trip_shape():
    mod, _ = load_module_with_stubbed_spidev()
    settings = mod.XMOSDeviceCntrl.decode_mic_output_settings(
        bytes([1, 0, 3, 0, 3, 0, 3, 0, 3])
    )
    assert settings.pack_extra_upsample_channels == 1
    assert settings.i2s_channel_map == (0, 3)
    assert settings.upsample_channel_map == (0, 3, 0, 3, 0, 3)


def test_set_mic_output_settings_partial_sends_new_resource_command():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue([0x02, 0x00, 0x00, 0])
    ok = dev.set_mic_output_settings_partial(i2s_channel_map=(2, 5))
    assert ok is True
    assert dev._spi.last_tx[0] == mod.AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_SETTINGS_RES_ID
    assert dev._spi.last_tx[1] == mod.AUDIO_PIPELINE_CONTROL.CMD_SET_SETTINGS_PARTIAL
    dev.close()


def test_get_mic_output_settings_reads_new_resource_command():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [mod.CntrlProto.RET_PAYLOAD_AVAILABLE, 0, 0, 3, 0, 3, 0, 3, 0, 3],
    )
    settings = dev.get_mic_output_settings()
    assert settings.i2s_channel_map == (0, 3)
    assert settings.pack_extra_upsample_channels == 0
    dev.close()


def test_encode_mic_output_partial_rejects_invalid_channel_index():
    mod, _ = load_module_with_stubbed_spidev()
    with pytest.raises(ValueError, match="channel index"):
        mod.XMOSDeviceCntrl.encode_mic_output_partial(i2s_channel_map=(0, 8))


def test_encode_mic_output_partial_requires_field():
    mod, _ = load_module_with_stubbed_spidev()
    with pytest.raises(ValueError, match="at least one"):
        mod.XMOSDeviceCntrl.encode_mic_output_partial()


def test_encode_speaker_settings_partial_contains_expected_mask():
    mod, _ = load_module_with_stubbed_spidev()
    payload = mod.XMOSDeviceCntrl.encode_speaker_settings_partial(
        eq_enabled=True,
        eq_profile_id=2,
    )
    assert payload == (0x03).to_bytes(4, "little") + bytes([1, 2, 0, 0])


def test_decode_speaker_settings_round_trip_shape():
    mod, _ = load_module_with_stubbed_spidev()
    settings = mod.XMOSDeviceCntrl.decode_speaker_settings(bytes([1, 2]))
    assert settings.eq_enabled == 1
    assert settings.eq_profile_id == 2


def test_set_speaker_settings_partial_sends_new_resource_command():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue([0x02, 0x00, 0x00, 0])
    ok = dev.set_speaker_settings_partial(eq_enabled=True, eq_profile_id=1)
    assert ok is True
    assert dev._spi.last_tx[0] == mod.AUDIO_PIPELINE_CONTROL.SPEAKER_SETTINGS_RES_ID
    assert dev._spi.last_tx[1] == mod.AUDIO_PIPELINE_CONTROL.CMD_SET_SETTINGS_PARTIAL
    dev.close()


def test_get_speaker_settings_reads_new_resource_command():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [mod.CntrlProto.RET_PAYLOAD_AVAILABLE, 1, 2],
    )
    settings = dev.get_speaker_settings()
    assert settings.eq_enabled == 1
    assert settings.eq_profile_id == 2
    dev.close()


def test_encode_mic_input_settings_partial_contains_expected_mask():
    mod, _ = load_module_with_stubbed_spidev()
    payload = mod.XMOSDeviceCntrl.encode_mic_input_settings_partial(
        mic_gain=0x40000000,
        ref_gain=0x20000000,
    )
    assert len(payload) == 20
    assert payload[:4] == (0x03).to_bytes(4, "little")
    assert payload[4:12] == (0x40000000).to_bytes(4, "little", signed=True) + (
        0x20000000
    ).to_bytes(4, "little", signed=True)


def test_encode_mic_input_settings_partial_requires_field():
    mod, _ = load_module_with_stubbed_spidev()
    with pytest.raises(ValueError, match="at least one"):
        mod.XMOSDeviceCntrl.encode_mic_input_settings_partial()


def test_decode_mic_input_settings_round_trip_shape():
    mod, _ = load_module_with_stubbed_spidev()
    settings = mod.XMOSDeviceCntrl.decode_mic_input_settings(
        struct.pack("<2i2B6B", 0x40000000, 0x20000000, 1, 0, 0, 1, 2, 3, 4, 5)
    )
    assert settings.mic_gain == 0x40000000
    assert settings.ref_gain == 0x20000000
    assert settings.ref_source_mode == 1
    assert settings.mic_source_mode == 0
    assert settings.ref_input_channel_map == (0, 1)
    assert settings.mic_input_channel_map == (2, 3, 4, 5)


def test_set_mic_input_settings_partial_sends_new_resource_command():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue([0x02, 0x00, 0x00, 0])
    ok = dev.set_mic_input_settings_partial(mic_gain=1, ref_gain=2)
    assert ok is True
    assert dev._spi.last_tx[0] == mod.AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID
    assert dev._spi.last_tx[1] == mod.AUDIO_PIPELINE_CONTROL.CMD_SET_SETTINGS_PARTIAL
    dev.close()


def test_get_mic_input_settings_reads_new_resource_command():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [mod.CntrlProto.RET_PAYLOAD_AVAILABLE]
        + list(struct.pack("<2i2B6B", 3, 4, 1, 1, 0, 1, 2, 3, 4, 5)),
    )
    settings = dev.get_mic_input_settings()
    assert settings.mic_gain == 3
    assert settings.ref_gain == 4
    assert settings.ref_source_mode == 1
    assert settings.mic_source_mode == 1
    assert settings.ref_input_channel_map == (0, 1)
    assert settings.mic_input_channel_map == (2, 3, 4, 5)
    dev.close()


def test_encode_mic_input_settings_partial_with_routing_fields():
    mod, _ = load_module_with_stubbed_spidev()
    payload = mod.XMOSDeviceCntrl.encode_mic_input_settings_partial(
        ref_source_mode=1,
        mic_source_mode=1,
        ref_input_channel_map=(0, 1),
        mic_input_channel_map=(2, 3, 4, 5),
    )
    field_mask = int.from_bytes(payload[:4], "little")
    assert field_mask == (
        mod.AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_REF_SOURCE_MODE
        | mod.AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_MIC_SOURCE_MODE
        | mod.AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_REF_INPUT_CHANNEL_MAP
        | mod.AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_MIC_INPUT_CHANNEL_MAP
    )
    assert payload[12:20] == bytes([1, 1, 0, 1, 2, 3, 4, 5])


def test_encode_mic_input_settings_partial_rejects_invalid_modes_or_maps():
    mod, _ = load_module_with_stubbed_spidev()
    with pytest.raises(ValueError, match="ref_source_mode"):
        mod.XMOSDeviceCntrl.encode_mic_input_settings_partial(ref_source_mode=2)
    with pytest.raises(ValueError, match="mic_source_mode"):
        mod.XMOSDeviceCntrl.encode_mic_input_settings_partial(mic_source_mode=2)
    with pytest.raises(ValueError, match="channel index"):
        mod.XMOSDeviceCntrl.encode_mic_input_settings_partial(
            ref_input_channel_map=(0, 8)
        )
    with pytest.raises(ValueError, match="must contain 4 values"):
        mod.XMOSDeviceCntrl.encode_mic_input_settings_partial(
            mic_input_channel_map=(0, 1)
        )


def test_get_available_mic_count_reads_single_byte_response():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [mod.CntrlProto.RET_PAYLOAD_AVAILABLE, 4],
    )

    count = dev.get_available_mic_count()

    assert count == 4
    assert dev._spi.last_tx[0] == 0
    assert dev._spi.last_tx[1] == 0
    dev.close()


def test_decode_doa_reading_round_trip_shape():
    mod, _ = load_module_with_stubbed_spidev()
    reading = mod.XMOSDeviceCntrl.decode_doa_reading(
        struct.pack("<iHBB", 1234, 9, 1, 0)
    )
    assert reading.doa_mrad == 1234
    assert reading.seq == 9
    assert reading.valid == 1


def test_get_doa_raw_reads_resource_232_command_3():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [mod.CntrlProto.RET_PAYLOAD_AVAILABLE]
        + list(struct.pack("<iHBB", 777, 3, 1, 0)),
    )

    reading = dev.get_doa_raw()

    assert reading.doa_mrad == 777
    assert reading.seq == 3
    assert reading.valid == 1
    assert dev._spi.last_tx[0] == 0
    assert dev._spi.last_tx[1] == 0
    dev.close()


def test_get_doa_smooth_reads_resource_232_command_4():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [mod.CntrlProto.RET_PAYLOAD_AVAILABLE]
        + list(struct.pack("<iHBB", -456, 11, 1, 0)),
    )

    reading = dev.get_doa_smooth()

    assert reading.doa_mrad == -456
    assert reading.seq == 11
    assert reading.valid == 1
    assert dev._spi.last_tx[0] == 0
    assert dev._spi.last_tx[1] == 0
    dev.close()


def test_decode_mic_input_debug_stats_shape():
    mod, _ = load_module_with_stubbed_spidev()
    stats = mod.XMOSDeviceCntrl.decode_mic_input_debug_stats(
        struct.pack("<IIIII", 123, 10, 20, 30, 40)
    )
    assert stats.frame_counter == 123
    assert stats.mic_mean_abs == (10, 20, 30, 40)


def test_get_mic_input_debug_stats_reads_resource_232_command_5():
    mod, _ = load_module_with_stubbed_spidev()
    dev = mod.XMOSDeviceCntrl()
    dev.open()
    dev._spi.queue(
        [0x02, 0x00, 0x00],
        [mod.CntrlProto.RET_PAYLOAD_AVAILABLE]
        + list(struct.pack("<IIIII", 7, 1, 2, 3, 4)),
    )

    stats = dev.get_mic_input_debug_stats()

    assert stats.frame_counter == 7
    assert stats.mic_mean_abs == (1, 2, 3, 4)
    dev.close()
