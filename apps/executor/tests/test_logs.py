"""Following a job's output: log.txt and its cap, the tail, and harness.job's protocol lines."""

import math
from pathlib import Path

from agentic_executor.logs import Done, Epoch, JobOutput, Step, jsonable
from agentic_executor.ports import LogLine
from executor_testkit import done_line, epoch_line, epoch_record, metric_line, step_line


def out(text: str, stream: str = "stdout") -> LogLine:
    return LogLine(stream, text)


def test_every_line_goes_to_the_log_until_the_cap_then_one_note(tmp_path: Path) -> None:
    log = tmp_path / "log.txt"
    output = JobOutput(log, max_log_bytes=20)
    for text in ["first", "second", "third line", "fourth", "fifth"]:
        output.feed(out(text))
    output.close()
    lines = log.read_text().splitlines()
    assert lines[:2] == ["first", "second"]
    assert len(lines) == 3 and lines[2].startswith("[log.txt ends here")
    assert output.tail.splitlines() == ["first", "second", "third line", "fourth", "fifth"]


def test_the_log_is_written_from_scratch(tmp_path: Path) -> None:
    """An executor that adopts a container replays its output from the start."""
    log = tmp_path / "log.txt"
    log.write_text("what an earlier executor wrote\n")
    output = JobOutput(log)
    output.feed(out("again from the start", "stderr"))
    output.close()
    assert log.read_text() == "again from the start\n"
    assert log.stat().st_mode & 0o777 == 0o644


def test_the_tail_keeps_the_last_lines_within_its_byte_budget(tmp_path: Path) -> None:
    output = JobOutput(tmp_path / "log.txt", tail_lines=3, tail_bytes=16)
    for index in range(10):
        output.feed(out(f"line {index}"))
    assert output.tail == "line 8\nline 9"  # three would be 21 bytes
    output.feed(out("x" * 100))
    assert output.tail == "x" * 15  # one line longer than the budget keeps its start
    output.feed(out("nul\0byte"))
    assert output.tail.endswith("nulbyte")
    output.close()


def test_the_tail_holds_200_lines_within_32_kib(tmp_path: Path) -> None:
    output = JobOutput(tmp_path / "log.txt")
    for index in range(500):
        output.feed(out(f"step {index}"))
    lines = output.tail.splitlines()
    assert len(lines) == 200 and lines[-1] == "step 499"
    for _ in range(100):
        output.feed(out("y" * 1000))
    assert len(output.tail.encode()) <= 32 * 1024
    output.close()


def test_metric_lines_become_records_and_epochs_are_counted(tmp_path: Path) -> None:
    output = JobOutput(tmp_path / "log.txt")
    step = output.feed(out(step_line(0, 20, 0.75)))
    assert isinstance(step, Step)
    assert step.record["kind"] == "train_step" and step.record["loss"] == 0.75
    first = output.feed(out(epoch_line(0)))
    second = output.feed(out(epoch_line(1)))
    assert isinstance(first, Epoch) and first.ordinal == 1
    assert isinstance(second, Epoch) and second.ordinal == 2
    assert {key: second.record[key] for key in ("epoch", "train", "val")} == {
        key: epoch_record(1)[key] for key in ("epoch", "train", "val")
    }
    assert output.epochs == 2
    output.close()


def test_malformed_and_unknown_metric_records_are_ignored(tmp_path: Path) -> None:
    output = JobOutput(tmp_path / "log.txt")
    assert output.feed(out("ARP-METRIC {not json")) is None
    assert output.feed(out('ARP-METRIC ["kind", "epoch"]')) is None
    assert output.feed(out(metric_line(kind="eval_step", step=3))) is None
    assert output.feed(out("ARP-METRIC" + epoch_line(0).removeprefix("ARP-METRIC "))) is None
    assert output.epochs == 0
    output.close()


def test_lines_that_only_look_like_protocol_lines_are_ignored(tmp_path: Path) -> None:
    """harness.job indents the training's own "ARP-" lines; protocol lines are on stdout."""
    output = JobOutput(tmp_path / "log.txt")
    assert output.feed(out("  " + epoch_line(0))) is None
    assert output.feed(out("  " + done_line(0))) is None
    assert output.feed(out(epoch_line(0), "stderr")) is None
    assert output.feed(out(done_line(0), "stderr")) is None
    assert output.feed(out("epoch 0 " + epoch_line(0))) is None
    assert output.epochs == 0 and output.exit_code is None
    output.close()
    assert len((tmp_path / "log.txt").read_text().splitlines()) == 5  # all of them are logged


def test_arp_done_gives_the_exit_code_once(tmp_path: Path) -> None:
    output = JobOutput(tmp_path / "log.txt")
    assert output.feed(out('ARP-DONE {"exit_code": "1"}')) is None
    assert output.feed(out("ARP-DONE {}")) is None
    assert output.feed(out('ARP-DONE {"exit_code": true}')) is None
    assert output.feed(out(done_line(-9))) == Done(-9)
    assert output.feed(out(done_line(0))) is None  # only the first counts
    assert output.exit_code == -9
    output.close()


def test_records_are_safe_to_store(tmp_path: Path) -> None:
    """Postgres refuses NUL characters and NaN in jsonb; a job's output may hold both."""
    output = JobOutput(tmp_path / "log.txt")
    record = output.feed(
        out(
            'ARP-METRIC {"kind": "epoch", "epoch": 0, "train": {"loss": NaN}, "val": '
            '{"loss": Infinity, "na\\u0000me": "a\\u0000b\\ud800"}}'
        )
    )
    assert isinstance(record, Epoch)
    assert record.record["train"] == {"loss": None}
    assert record.record["val"] == {"loss": None, "name": "ab?"}
    output.close()
    assert jsonable([1.5, -math.inf, {"k": [math.nan]}]) == [1.5, None, {"k": [None]}]
