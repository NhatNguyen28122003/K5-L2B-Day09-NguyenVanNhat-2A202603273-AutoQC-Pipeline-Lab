"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fmt(v):
    return f"{v:.6f}".rstrip("0").rstrip(".") if v else "0"


def _clip(text):
    """Cắt box về [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích."""
    c, cx, cy, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    nw, nh = x2 - x1, y2 - y1
    if nw <= 1e-9 or nh <= 1e-9:
        return None
    return " ".join([str(c), _fmt((x1 + x2) / 2), _fmt((y1 + y2) / 2), _fmt(nw), _fmt(nh)])


def _remove_image(ds, stem):
    imgs = [p for p in ds.image_files() if p.stem == stem]
    lab = ds.label_path(stem)
    removed = [p.name for p in imgs] + ([lab.name] if lab.exists() else [])
    for p in imgs:
        p.unlink()
    if lab.exists():
        lab.unlink()
    return removed


def _rename_classes(ds, cfg):
    data = {}
    if ds.yaml_path.exists():
        data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
    before = ds.yaml_names()
    want = {i: n for i, n in enumerate(cfg["classes"])}
    if before == want:
        return None
    data["names"] = want
    ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"image": "data.yaml", "line": "", "action": "rename_classes",
            "before": str(list(before.values())), "after": str(cfg["classes"])}


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1) Xoá ảnh trước — mọi issue dòng của ảnh đã xoá sẽ bị bỏ qua.
    removed = set()
    for i in errors:
        if _is_remove(i.code) and i.image not in removed:
            files = _remove_image(ds, i.image)
            removed.add(i.image)
            if files:
                fixes.append({"image": i.image, "line": "", "action": "remove_image",
                              "before": "; ".join(files) + f" ({i.code})", "after": "(đã xoá)"})

    # 2) data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        f = _rename_classes(ds, cfg)
        if f:
            fixes.append(f)

    # 3) Ảnh chưa có nhãn: chuyển người gán, KHÔNG tạo file.
    seen_missing = set()
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and i.image not in seen_missing:
            seen_missing.add(i.image)
            if not ds.label_path(i.image).exists():
                fixes.append({"image": i.image, "line": "", "action": "needs_label",
                              "before": "(không có file)", "after": "chuyển người gán"})

    # 4) Lỗi theo dòng: gom theo file, dùng số dòng GỐC, ghi lại một lần.
    by_file = defaultdict(lambda: defaultdict(set))   # stem -> line -> {codes}
    for i in errors:
        if i.line is None or i.image in removed:
            continue
        if i.code in DROP_CODES or i.code in CLIP_CODES:
            by_file[i.image][int(i.line)].add(i.code)

    for stem in sorted(by_file):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        orig = path.read_text(encoding="utf-8", errors="replace").splitlines()
        new = list(orig)                      # giữ đúng vị trí -> số dòng không lệch
        drop = set()
        for ln in sorted(by_file[stem]):
            if not 1 <= ln <= len(orig) or not orig[ln - 1].strip():
                continue
            codes, text = by_file[stem][ln], orig[ln - 1]
            if codes & DROP_CODES:            # xoá thắng cắt
                drop.add(ln)
                fixes.append({"image": stem, "line": ln, "action": "drop_line", "before": text, "after": ""})
                continue
            try:
                clipped = _clip(text)
            except ValueError:                # không parse được thì không cắt được: xoá
                clipped = None
            if clipped is None:
                drop.add(ln)
                fixes.append({"image": stem, "line": ln, "action": "drop_line", "before": text, "after": ""})
            elif clipped != text:
                new[ln - 1] = clipped
                fixes.append({"image": stem, "line": ln, "action": "clip_box", "before": text, "after": clipped})
        if drop or new != orig:
            out = [t for n, t in enumerate(new, 1) if n not in drop]
            path.write_text("".join(t + "\n" for t in out), encoding="utf-8")

    return fixes
