"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


CHECK = "second_opinion"


def _numbered_valid_boxes(ds, stem):
    """[(số dòng gốc, (id, cx, cy, w, h))] — cùng tiêu chí với `ds.valid_boxes` nhưng giữ số dòng."""
    out = []
    n_classes = len(ds.classes)
    for lineno, text in ds.read_label_lines(stem) or []:
        try:
            b = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= b[0] < n_classes:
            out.append((lineno, b))
    return out


def run(ds, cfg, preds=None):
    """So nhãn với dự đoán của model lớn hơn; chỉ sinh cảnh báo (WARN) cho người duyệt."""
    sc = cfg["second_opinion"]                     # mọi ngưỡng lấy từ config
    conf_min = float(sc["conf"])
    min_area_px = float(sc["min_area_px"])
    fp_conf = float(sc["fp_conf"])
    iou_missing = float(sc["iou_missing"])
    iou_match = float(sc["iou_match"])
    iou_loose = float(sc["iou_loose"])

    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []

    def add(code, stem, msg, line=None, extra=None):
        issues.append(Issue(CHECK, WARN, code, stem, msg, line, extra or {}))

    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or ds.read_label_lines(stem) is None:
            continue                               # không có dự đoán hoặc không có file nhãn -> bỏ qua
        size = ds.image_size(stem)
        if size is None:
            continue                               # ảnh hỏng: không tính được diện tích px (check images sẽ báo)
        W, H = size

        labels = _numbered_valid_boxes(ds, stem)
        rows = []
        for r in preds[stem] or []:
            try:
                c, cf, cx, cy, w, h = r
                rows.append((int(c), float(cf), (float(cx), float(cy), float(w), float(h))))
            except (TypeError, ValueError):
                continue                           # dòng dự đoán hỏng: bỏ qua

        # 1) Từng dự đoán đáng tin (conf đủ cao, đủ lớn) -> MISSING / LOOSE_BOX / WRONG_CLASS
        for c, cf, box in rows:
            if cf < conf_min or box[2] * W * box[3] * H < min_area_px:
                continue
            cands = [(iou_xywh(box, lb[1:]), lb[0]) for _, lb in labels]
            cands = [(iou, lc) for iou, lc in cands if iou >= iou_missing]
            if not cands:
                add("POSSIBLE_MISSING", stem,
                    f"model thấy {_name(ds, c)} (conf {cf:.2f}) nhưng nhãn không có box nào ở đó",
                    extra={"conf": round(cf, 4), "class_id": c, "box": list(box)})
                continue
            same = [iou for iou, lc in cands if lc == c]
            if same:
                best = max(same)
                if best < iou_loose:
                    add("POSSIBLE_LOOSE_BOX", stem,
                        f"box {_name(ds, c)} lệch/lỏng so với model (IoU {best:.2f} < {iou_loose})",
                        extra={"conf": round(cf, 4), "iou": round(best, 4), "class_id": c})
                continue                           # nhãn đúng lớp đã phủ vật này
            best_iou, best_cls = max(cands)
            if best_iou >= iou_match:
                add("POSSIBLE_WRONG_CLASS", stem,
                    f"nhãn ghi {_name(ds, best_cls)} nhưng model nói {_name(ds, c)} (conf {cf:.2f}, IoU {best_iou:.2f})",
                    extra={"conf": round(cf, 4), "iou": round(best_iou, 4),
                           "label_class": best_cls, "pred_class": c})
            # khác lớp với IoU trong [iou_missing, iou_match): mơ hồ -> không cờ

        # 2) Từng box nhãn không khớp dự đoán nào (conf >= fp_conf, không lọc diện tích) -> FALSE_POS
        loose_preds = [box for _, cf, box in rows if cf >= fp_conf]
        for lineno, lb in labels:
            best = max((iou_xywh(lb[1:], box) for box in loose_preds), default=0.0)
            if best < iou_missing:
                add("POSSIBLE_FALSE_POS", stem,
                    f"box {_name(ds, lb[0])} ở dòng {lineno} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                    line=lineno, extra={"iou": round(best, 4), "class_id": lb[0]})

    return issues


def _name(ds, c):
    return ds.classes[c] if 0 <= c < len(ds.classes) else f"lớp {c}"
