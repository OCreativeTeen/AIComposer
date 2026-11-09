"""t308u: 节目生成一次性/二次提交、顺序生成、多结果存储。不连 NotebookLM。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import threading
import time
from types import SimpleNamespace

import tempfile

from utility.program_media import (
    append_program_media,
    clamp_studio_times,
    coerce_program_media_list,
    file_result_paths,
    get_primary_program_media,
    get_program_media_list,
    infographic_candidates_side_by_side,
    infographic_pick_thumb_size,
    list_existing_program_media,
    order_after_selection,
    remove_program_media,
    run_sequential_generations,
    settle_generated_file,
    studio_times_from_extra,
    unique_dest_path,
)


def _touch(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(os.path.basename(path))
    return path


def test_coerce_scalar_and_list_no_data_loss():
    assert coerce_program_media_list("/tmp/old.pdf") == ["/tmp/old.pdf"]
    assert coerce_program_media_list(["/a.pdf", "", "/b.pdf"]) == ["/a.pdf", "/b.pdf"]
    assert coerce_program_media_list(None) == []
    assert coerce_program_media_list("") == []
    item = {"slide": "/legacy/one.pdf"}
    assert get_program_media_list(item, "slides") == ["/legacy/one.pdf"]


def test_old_scalar_compat_then_append_newest_first():
    tmp_path = Path(tempfile.mkdtemp())
    first = _touch(str(tmp_path / "old.pdf"))
    second = _touch(str(tmp_path / "new.pdf"))
    item = {"slide": first}
    assert get_primary_program_media(item, "slides") == os.path.abspath(first)
    append_program_media(item, "slides", second)
    listed = get_program_media_list(item, "slides")
    assert listed[0] == os.path.abspath(second)
    assert os.path.abspath(first) in listed
    assert isinstance(item["slide"], list)


def test_repeated_media_newest_first_all_kinds():
    tmp_path = Path(tempfile.mkdtemp())
    item = {}
    for kind, prefix in (
        ("slides", "s"),
        ("audio_overview", "a"),
        ("video_overview", "v"),
    ):
        p1 = _touch(str(tmp_path / f"{prefix}1.bin"))
        p2 = _touch(str(tmp_path / f"{prefix}2.bin"))
        p3 = _touch(str(tmp_path / f"{prefix}3.bin"))
        append_program_media(item, kind, p1)
        append_program_media(item, kind, p2)
        append_program_media(item, kind, p3)
        paths = list_existing_program_media(item, kind)
        assert [os.path.basename(p) for p in paths] == [f"{prefix}3.bin", f"{prefix}2.bin", f"{prefix}1.bin"]
        assert get_primary_program_media(item, kind) == os.path.abspath(p3)


def test_remove_preserves_others():
    tmp_path = Path(tempfile.mkdtemp())
    item = {}
    a = _touch(str(tmp_path / "a.m4a"))
    b = _touch(str(tmp_path / "b.m4a"))
    append_program_media(item, "audio_overview", a)
    append_program_media(item, "audio_overview", b)
    remove_program_media(item, "audio_overview", b)
    assert get_program_media_list(item, "audio_overview") == [os.path.abspath(a)]


def test_run_sequential_count_1():
    calls = []

    def generate(i):
        calls.append(i)
        return f"/tmp/once-{i}.pdf"

    paths, err, cancelled = run_sequential_generations(generate, 1)
    assert paths == ["/tmp/once-0.pdf"]
    assert err is None
    assert cancelled is False
    assert calls == [0]


def test_run_sequential_count_2_first_completes_before_second():
    order = []

    def generate(i):
        order.append(("start", i))
        time.sleep(0.02)
        order.append(("done", i))
        return f"/tmp/twice-{i}.pdf"

    paths, err, cancelled = run_sequential_generations(generate, 2)
    assert err is None
    assert cancelled is False
    assert paths == ["/tmp/twice-0.pdf", "/tmp/twice-1.pdf"]
    assert order == [("start", 0), ("done", 0), ("start", 1), ("done", 1)]


def test_run_sequential_not_parallel():
    active = 0
    max_active = 0

    def generate(i):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.03)
        active -= 1
        return f"/tmp/par-{i}.pdf"

    paths, err, cancelled = run_sequential_generations(generate, 2)
    assert paths == ["/tmp/par-0.pdf", "/tmp/par-1.pdf"]
    assert err is None
    assert cancelled is False
    assert max_active == 1


def test_error_second_preserves_first():
    def generate(i):
        if i == 0:
            return "/tmp/keep.pdf"
        raise RuntimeError("second failed")

    paths, err, cancelled = run_sequential_generations(generate, 2)
    assert paths == ["/tmp/keep.pdf"]
    assert isinstance(err, RuntimeError)
    assert "second failed" in str(err)
    assert cancelled is False


def test_cancel_prevents_second():
    calls = []
    cancel_after_first = {"yes": False}

    def generate(i):
        calls.append(i)
        cancel_after_first["yes"] = True
        return f"/tmp/c{i}.pdf"

    paths, err, cancelled = run_sequential_generations(
        generate, 2, should_cancel=lambda: cancel_after_first["yes"]
    )
    assert paths == ["/tmp/c0.pdf"]
    assert err is None
    assert cancelled is True
    assert calls == [0]


def test_same_artifact_rejected():
    def generate(i):
        return "/tmp/same.pdf"

    paths, err, cancelled = run_sequential_generations(generate, 2)
    assert paths == ["/tmp/same.pdf"]
    assert err is not None
    assert cancelled is False


def test_unique_dest_and_settle():
    tmp_path = Path(tempfile.mkdtemp())
    src_dir = tmp_path / "dl"
    dest_dir = tmp_path / "work"
    src_dir.mkdir()
    dest_dir.mkdir()
    first = _touch(str(src_dir / "Infographic.png"))
    settled1 = settle_generated_file(first, str(dest_dir))
    assert os.path.isfile(settled1)
    assert os.path.dirname(settled1) == str(dest_dir)
    assert settled1 != first
    # already in dest: do not stamp again
    assert settle_generated_file(settled1, str(dest_dir)) == settled1
    second_src = _touch(str(src_dir / "Infographic.png"))
    settled2 = settle_generated_file(second_src, str(dest_dir))
    assert settled1 != settled2
    assert os.path.isfile(settled1) and os.path.isfile(settled2)
    names = [os.path.basename(settled1), os.path.basename(settled2)]
    assert names[0] < names[1] or names[0] != names[1]
    # make_studio 可能直接下载到 working：同目录未加戳的文件也要改名，避免第二次覆盖
    inside = _touch(str(dest_dir / "Infographic.png"))
    settled3 = settle_generated_file(inside, str(dest_dir))
    assert settled3 != inside
    assert not os.path.exists(inside)
    assert os.path.isfile(settled3)


def test_infographic_layout_16_9_stack():
    assert infographic_candidates_side_by_side("1920x1080") is False
    assert infographic_candidates_side_by_side("16:9") is False


def test_infographic_layout_9_16_side_by_side():
    assert infographic_candidates_side_by_side("1080x1920") is True
    assert infographic_candidates_side_by_side("9:16") is True
    assert infographic_candidates_side_by_side("portrait") is True


def test_infographic_selection_handler_orders_selected_first():
    tmp_path = Path(tempfile.mkdtemp())
    a = _touch(str(tmp_path / "a.png"))
    b = _touch(str(tmp_path / "b.png"))
    ordered = order_after_selection([a, b], a)
    assert ordered[0] == a
    assert ordered[1] == b
    ordered = order_after_selection([a, b], b)
    assert ordered[0] == b
    assert ordered[1] == a
    item = {"cover_image": []}
    # 模拟提交后入库：先写入非选中，再写入选中 → 选中成为当前
    for path in reversed(ordered):
        item["cover_image"] = [path] + [p for p in item["cover_image"] if p != path]
    assert item["cover_image"][0] == ordered[0]


def test_file_result_paths_and_studio_times():
    assert file_result_paths(None) == []
    assert file_result_paths("/tmp/one.pdf") == ["/tmp/one.pdf"]
    assert file_result_paths(SimpleNamespace(paths=["/a", "/b"])) == ["/a", "/b"]
    assert studio_times_from_extra({"studio_times": 2}) == 2
    assert studio_times_from_extra({"studio_times": "1"}) == 1
    assert studio_times_from_extra({}) == 1
    assert studio_times_from_extra(None) == 1
    assert studio_times_from_extra({"studio_times": 3}) == 3
    assert studio_times_from_extra({"studio_times": "3"}) == 3
    assert studio_times_from_extra({"studio_times": 4}) == 3
    assert studio_times_from_extra({"studio_times": 0}) == 1
    assert clamp_studio_times(3) == 3
    assert clamp_studio_times("2") == 2
    assert clamp_studio_times(-1) == 1
    assert clamp_studio_times("nope") == 1


def test_run_sequential_count_3_first_completes_before_next():
    order = []

    def generate(i):
        order.append(("start", i))
        time.sleep(0.015)
        order.append(("done", i))
        return f"/tmp/thrice-{i}.pdf"

    paths, err, cancelled = run_sequential_generations(generate, 3)
    assert err is None
    assert cancelled is False
    assert paths == ["/tmp/thrice-0.pdf", "/tmp/thrice-1.pdf", "/tmp/thrice-2.pdf"]
    assert order == [
        ("start", 0), ("done", 0),
        ("start", 1), ("done", 1),
        ("start", 2), ("done", 2),
    ]


def test_error_third_preserves_first_two():
    def generate(i):
        if i < 2:
            return f"/tmp/keep-{i}.pdf"
        raise RuntimeError("third failed")

    paths, err, cancelled = run_sequential_generations(generate, 3)
    assert paths == ["/tmp/keep-0.pdf", "/tmp/keep-1.pdf"]
    assert isinstance(err, RuntimeError)
    assert "third failed" in str(err)
    assert cancelled is False


def test_cancel_after_two_of_three_keeps_partial():
    calls = []
    cancel_after = {"n": 0}

    def generate(i):
        calls.append(i)
        cancel_after["n"] += 1
        return f"/tmp/c3-{i}.pdf"

    paths, err, cancelled = run_sequential_generations(
        generate, 3, should_cancel=lambda: cancel_after["n"] >= 2
    )
    assert paths == ["/tmp/c3-0.pdf", "/tmp/c3-1.pdf"]
    assert err is None
    assert cancelled is True
    assert calls == [0, 1]


def test_same_artifact_rejected_on_third():
    def generate(i):
        if i < 2:
            return f"/tmp/uniq-{i}.pdf"
        return "/tmp/uniq-0.pdf"

    paths, err, cancelled = run_sequential_generations(generate, 3)
    assert paths == ["/tmp/uniq-0.pdf", "/tmp/uniq-1.pdf"]
    assert err is not None
    assert cancelled is False


def test_infographic_three_image_layout_fits_screen():
    assert infographic_candidates_side_by_side("1920x1080") is False
    assert infographic_candidates_side_by_side("1080x1920") is True
    stack2 = infographic_pick_thumb_size("1920x1080", 2)
    stack3 = infographic_pick_thumb_size("16:9", 3)
    side2 = infographic_pick_thumb_size("1080x1920", 2)
    side3 = infographic_pick_thumb_size("9:16", 3)
    assert stack3[1] <= stack2[1]
    assert side3[0] <= side2[0]
    # three landscape stacked: total height under a typical 1080p usable area
    assert stack3[1] * 3 + 180 <= 1080
    assert stack3[0] <= 560
    # three portraits side-by-side: total width under a typical 1366-wide window
    assert side3[0] * 3 + 160 <= 1366
    assert side3[1] <= 560


def test_infographic_selection_orders_chosen_first_of_three():
    tmp_path = Path(tempfile.mkdtemp())
    a = _touch(str(tmp_path / "a.png"))
    b = _touch(str(tmp_path / "b.png"))
    c = _touch(str(tmp_path / "c.png"))
    ordered = order_after_selection([a, b, c], b)
    assert ordered[0] == b
    assert ordered[1:] == [a, c]
    item = {"cover_image": []}
    for path in reversed(ordered):
        item["cover_image"] = [path] + [p for p in item["cover_image"] if p != path]
    assert item["cover_image"][0] == b
    assert item["cover_image"] == [b, a, c]


def test_submit_dialog_has_three_compact_buttons():
    src = Path(ROOT, "gui/slide_prompt_dialog.py").read_text(encoding="utf-8")
    assert 'text="一次提交"' in src
    assert 'text="二次提交"' in src
    assert 'text="三次提交"' in src
    assert "一次性提交" not in src
    assert "copy_prompt(3)" in src
    assert "compact=True" in src


def test_cover_video_not_a_program_kind():
    item = {"cover_video": "/film.mp4"}
    assert get_program_media_list(item, "video_overview") == []
    append_program_media(item, "video_overview", "/overview.mp4")
    assert item["cover_video"] == "/film.mp4"
    assert item["video_overview"][0].endswith("overview.mp4")


def test_unique_dest_path_collision():
    tmp_path = Path(tempfile.mkdtemp())
    dest1 = unique_dest_path(str(tmp_path), "clip.mp4")
    _touch(dest1)
    dest2 = unique_dest_path(str(tmp_path), "clip.mp4")
    assert dest1 != dest2


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(failed)
