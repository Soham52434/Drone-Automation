from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from drone_security.config import AppConfig
from drone_security.indexing import ChunkWriter, SessionStore
from drone_security.models import FramePacket
from drone_security.pipeline import SessionManager


def make_packet(timestamp_ms: int, index: int = 0, width: int = 64, height: int = 48) -> FramePacket:
    image = np.full((height, width, 3), index % 255, dtype=np.uint8)
    return FramePacket(timestamp_ms=timestamp_ms, frame_index=index, image=image)


def make_packets(count: int, interval_ms: int, start_ms: int = 0) -> list[FramePacket]:
    return [make_packet(start_ms + i * interval_ms, i) for i in range(count)]


def write_test_video(path: Path, seconds: float, fps: int = 15, width: int = 160, height: int = 120) -> Path:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        for i in range(int(seconds * fps)):
            image = np.zeros((height, width, 3), dtype=np.uint8)
            image[:, : (i * 3) % width] = (40, 120, 200)
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            frame.pts = i
            frame.time_base = Fraction(1, fps)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    return AppConfig(data_dir=tmp_path / "data")


@pytest.fixture
def store(config: AppConfig):
    store = SessionStore(config.db_path)
    yield store
    store.close()


@pytest.fixture
def manager(config: AppConfig, store: SessionStore) -> SessionManager:
    return SessionManager(config, store, ChunkWriter())


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_test_video(tmp_path_factory.mktemp("media") / "sample.mp4", seconds=12)
