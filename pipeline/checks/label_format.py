"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


CHECK = "label_format"


def _overflow(cx, cy, w, h):
    """Mức tràn lớn nhất của 4 mép box ra ngoài [0, 1] (0 nếu nằm gọn trong ảnh)."""
    left, right = cx - w / 2, cx + w / 2
    top, bottom = cy - h / 2, cy + h / 2
    return max(0.0, -left, right - 1.0, -top, bottom - 1.0)


def run(ds, cfg):
    """Kiểm từng dòng của mọi file nhãn trong `labels/`. Chỉ ĐỌC file, không sửa gì."""
    lc = cfg["label_format"]                       # mọi ngưỡng lấy từ config, không viết cứng
    overflow_tol = float(lc["overflow_tol"])
    dup_box_iou = float(lc["dup_box_iou"])
    min_box_px = float(lc["min_box_px"])
    max_box_frac = float(lc["max_box_frac"])
    n_classes = len(ds.classes)

    issues = []

    def add(sev, code, stem, line, msg, extra=None):
        issues.append(Issue(CHECK, sev, code, stem, msg, line, extra or {}))

    for lab in ds.label_files():
        stem = lab.stem
        # read_label_lines bỏ dòng trống nhưng GIỮ số dòng gốc (đếm từ 1)
        lines = ds.read_label_lines(stem) or []
        size = None                               # (rộng, cao) px — chỉ mở ảnh khi cần
        seen = []                                 # các box hợp lệ ở dòng trước: (lineno, box)

        for lineno, text in lines:
            # 1) Định dạng: đúng 5 cột số, id nguyên, không nan/inf. Dòng hỏng -> báo rồi bỏ qua.
            try:
                c, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", stem, lineno, f"dòng sai định dạng ({e}): {text.strip()!r}")
                continue

            # 2) ID lớp phải nằm trong 0..len(classes)-1
            if not 0 <= c < n_classes:
                add(ERROR, "BAD_CLASS_ID", stem, lineno,
                    f"id lớp {c} ngoài khoảng 0..{n_classes - 1}", {"class_id": c})
                continue

            # 3) Box rỗng: chiều rộng/cao không dương -> không kiểm hình học tiếp
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", stem, lineno, f"box rỗng: w={w}, h={h} (phải > 0)")
                continue

            # 4) Tràn ảnh: mép box vượt [0,1] quá overflow_tol (chạm đúng biên thì ổn)
            over = _overflow(cx, cy, w, h)
            if over > overflow_tol:
                add(ERROR, "BOX_OUT_OF_IMAGE", stem, lineno,
                    f"box tràn ra ngoài ảnh {over:.4f} (> tol {overflow_tol})", {"overflow": over})

            # 5) Box lặp: cùng lớp với một dòng TRƯỚC và IoU > dup_box_iou -> báo dòng SAU
            box = (cx, cy, w, h)
            for prev_line, (pc, pbox) in seen:
                if pc == c:
                    iou = iou_xywh(box, pbox)
                    if iou > dup_box_iou:
                        add(ERROR, "DUP_BOX", stem, lineno,
                            f"trùng box dòng {prev_line} (lớp {c}, IoU={iou:.3f} > {dup_box_iou})",
                            {"dup_of_line": prev_line, "iou": iou})
                        break
            seen.append((lineno, (c, box)))

            # 6) Box quá nhỏ: cạnh ngắn nhất theo pixel < min_box_px (cần kích thước ảnh)
            if size is None:
                size = ds.image_size(stem) or ()
            if size:
                iw, ih = size
                short_px = min(w * iw, h * ih)
                if short_px < min_box_px:
                    add(WARN, "BOX_TINY", stem, lineno,
                        f"cạnh ngắn của box {short_px:.1f}px < {min_box_px}px", {"short_px": short_px})

            # 7) Box quá lớn: diện tích chuẩn hoá w*h > max_box_frac
            area = w * h
            if area > max_box_frac:
                add(WARN, "BOX_HUGE", stem, lineno,
                    f"box chiếm {area:.1%} ảnh (> {max_box_frac:.0%})", {"area_frac": area})

    return issues
