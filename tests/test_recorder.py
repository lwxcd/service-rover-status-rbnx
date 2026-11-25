import json
import os
from datetime import datetime

from rover_status.core import CSV_COLUMNS
from rover_status.node import Recorder


def test_daily_csv_and_json(tmp_path, sample_status):
    recorder = Recorder(str(tmp_path), retention_days=0)
    recorder.write(sample_status)
    recorder.write(sample_status)
    recorder.close()
    day = datetime.now().strftime("%Y%m%d")
    path = tmp_path / f"rover_status_{day}.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == CSV_COLUMNS
    assert len(lines) == 3
    data = json.loads((tmp_path / "rover_status.json").read_text(encoding="utf-8"))
    assert data["t_wall"] == sample_status["t_wall"]
    assert recorder.current_path is None


def test_restart_appends_to_the_same_day(tmp_path, sample_status):
    first = Recorder(str(tmp_path), retention_days=0)
    first.write(sample_status)
    first.close()
    second = Recorder(str(tmp_path), retention_days=0)
    second.write(sample_status)
    second.close()
    day = datetime.now().strftime("%Y%m%d")
    lines = (tmp_path / f"rover_status_{day}.csv").read_text(
        encoding="utf-8").splitlines()
    assert lines[0].split(",") == CSV_COLUMNS
    assert len(lines) == 3


def test_retention_prunes_only_old_csv(tmp_path, sample_status):
    old = tmp_path / "rover_status_20000101.csv"
    old.write_text("old", encoding="utf-8")
    os.utime(old, (0, 0))
    keep = tmp_path / "rover_status.json"
    keep.write_text("{}", encoding="utf-8")
    Recorder(str(tmp_path), retention_days=1)
    assert not old.exists()
    assert keep.exists()
    assert not any(tmp_path.glob("rover_status_2*.csv"))
