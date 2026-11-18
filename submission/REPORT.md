# Báo cáo Day 09 — Nguyen Van Nhat, 2A202603273

## 1. Kết luận trước
Pipeline kết luận **Release** (`08_summary.json`). **224 ảnh vào → 193 ảnh ra** `export/clean_v1` (31 ảnh bị loại ở bước 1).
Sau autofix + 80 ảnh người duyệt, danh sách v3 còn **0 lỗi bắt buộc**; còn **13/193 ảnh (6,74%)** có cảnh báo chưa duyệt, dưới ngưỡng Hold 10%.

## 2. Lỗi và phân việc
Theo `02_error_list_v1` (mẫu số: 224 ảnh quét; số = dòng lỗi / số ảnh).

| Mã lỗi | Số dòng (ảnh) | Ai sửa | Vì sao |
|---|---:|---|---|
| LEAK_TEST | 11 (11) | máy (loại ảnh) | trùng ảnh kho test/val → giữ lại là rò rỉ đánh giá |
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR | 8 (8) / 7 (7) | máy (loại ảnh) | trùng byte / pHash ≤ 16, giữ ảnh gốc |
| BAD_SIZE / CORRUPT_IMAGE | 3 (3) / 2 (2) | máy (loại ảnh) | cạnh < 250px / không mở được, không có gì để sửa |
| BAD_CLASS_ID, BAD_FORMAT, BOX_ZERO, DUP_BOX | 6 / 3 / 4 / 7 | máy (`drop_line`, 20 dòng) | dòng hỏng theo quy tắc, xoá dòng rồi đẩy ảnh vào hàng đợi (`FIXED_DROP_LINE`) |
| BOX_OUT_OF_IMAGE | 8 (8) | máy (`clip_box`, 8 dòng) | tràn mép: kẹp về [0,1] là an toàn |
| BAD_CLASS_NAME | 2 (data.yaml) | máy (`rename_classes`) | `Person`/`Bus` → `person`/`bus`, chỉ khác hoa/thường |
| MISSING_LABEL_FILE | 6 (6) | **người** (`NEEDS_LABEL`) | máy không biết ảnh có vật gì |
| POSSIBLE_WRONG_CLASS / MISSING / FALSE_POS / LOOSE_BOX | 13 / 32 / 28 / 11 | **người** | ý nghĩa nhãn, model lớn chỉ là ý kiến thứ hai |
| BOX_TINY, BOX_HUGE, EMPTY_LABEL, CLASS_RARE | 6 / 3 / 11 / 4 | người (nếu còn ngân sách) | cảnh báo quy tắc dự án, không chắc là sai |

`05_review_queue.csv` (98 ảnh) xếp theo tổng trọng số mã lỗi: đầu hàng là `img_0020` (11,52 = FIXED_DROP_LINE 2 + MISSING 2 + WRONG_CLASS 3, nhân theo conf) rồi 6 ảnh `NEEDS_LABEL` (10) — ảnh thiếu nhãn phải xử lý trước vì nếu không gate sẽ Rework. Sau đó là các ảnh có lỗi ngữ nghĩa trọng số cao (WRONG_CLASS 3, MISSING/FALSE_POS 2).
Với ngân sách 80 ảnh, người duyệt **67 ảnh có lỗi ngữ nghĩa, 76/78 cờ ngữ nghĩa** trong hàng đợi (đủ 13 WRONG_CLASS, 32 MISSING, 11 LOOSE_BOX, 20/28 FALSE_POS); 18 ảnh cuối hàng (ưu tiên ≤ 2,0, chủ yếu `FIXED_DROP_LINE`) không được xem.

## 3. Calibration (2 ngưỡng)
Đo trên `data/calib` (lỗi chèn có đáp án), `calibration_report.md`.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **16** | NEAR: 1,00/0,50 → 1,00/0,83 (EXACT giữ 1,00/1,00) | 16 là giá trị duy nhất đạt recall 0,83 mà precision chưa giảm; 20 làm hỏng cả EXACT (R 0,33) |
| `second_opinion.conf` | 0.25 | **0.8** | WRONG_CLASS 0,56/0,83 → 1,00/0,83; MISSING 0,50/1,00 → 0,67/0,75 | người duyệt chỉ có 80 ảnh nên ưu tiên precision; đổi lại mất 2/8 MISSING và LOOSE_BOX 0,29/0,40 → 0,50/0,20 |

**Kết luận nhạy với `conf`:** chạy lại pipeline (budget 80) chỉ đổi `conf` thì tỉ lệ ảnh còn cảnh báo chưa duyệt là: 0,25 → 53/193 (27,5%), 0,5 → 40/193 (20,7%), 0,6 → 34/193 (17,6%), 0,7 → 25/193 (13,0%) — **tất cả là Hold**; chỉ 0,8 → 13/193 (6,7%) mới Release. Mình vẫn chọn 0,8 vì đó là giá trị tốt nhất trên calib (tổng F1 4 mã: 2,39 ở 0,8 so với 2,18 ở 0,7 và 2,12 ở 0,6), không phải để qua cổng; nhưng phải nói rõ: **Release đạt được một phần nhờ bớt cờ** (MISSING recall 1,00 → 0,75), tức một số lỗi thiếu nhãn không được báo chứ không phải đã được sửa.

**Chỗ calibration đánh lừa:** trên bộ calib, `phash_dist=16` có precision 1,00, nhưng trên lô thật 3/7 cặp `DUP_IMAGE_NEAR` nằm đúng ở khoảng cách 16. Mở xem: `img_0084`↔`img_0074` đúng là ảnh lật gương, nhưng `img_0011`↔`img_0008` (tennis vs trượt tuyết) và `img_0177`↔`img_0113` (lướt sóng vs người ngồi bàn) **hoàn toàn khác nhau** → 2 ảnh tốt bị loại oan (precision thật ≈ 5/7). Bộ calib chỉ có 6 ảnh near-dup nên P=1,00 không đáng tin; ngưỡng nằm sát mép (16 tốt, 20 sập). Ngoài ra `img_0177` bị loại vì "trùng" `img_0113`, mà `img_0113` cũng bị loại (BAD_SIZE) → mất cả hai. `POSSIBLE_FALSE_POS` không đổi theo conf (P 0,31 mọi mức) vì dùng `fp_conf` cố định 0.1.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` → kết luận **REWORK** ("Còn 6 lỗi bắt buộc trên 6 ảnh/tệp (mã: MISSING_LABEL_FILE)", thêm 81/193 = 41,97% ảnh còn cảnh báo), **mã thoát 20**, log "Bước 5/5 KHÔNG xuất", và `work/exp_nb` **không tồn tại**. Gate chặn đúng.

(b) Điểm mù có bằng chứng:
1. **Box lỏng nhẹ:** `POSSIBLE_LOOSE_BOX` recall chỉ **0,20 (1/5)** trên calib ở conf 0,8 — box lệch nhưng IoU vẫn ≥ 0,5 thì lọt hoàn toàn.
2. **Nhầm lớp mà model cũng nhầm / không tự tin:** WRONG_CLASS recall 0,83 (1/6 lọt ở mọi conf); trên lô thật v3 còn `img_0078` "truck nhưng model nói car (conf 0,83)" — truck/car vốn dễ lẫn, model không phải đáp án.
3. **Ảnh trùng biến đổi mạnh:** 1/6 near-dup calib vẫn lọt ở 16; tăng ngưỡng lên 20 thì sập. pHash không bắt được crop/xoay mạnh mà không gây báo nhầm (xem mục 3).
4. **FALSE_POS báo nhầm nhiều** (P 0,31): 8 cờ FALSE_POS cuối hàng đợi + 11 dòng trong v3 không được người xem.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Chưa chạy**: chưa có GPU/Colab trong thời gian làm bài (`submission/results/` trống). Nếu chạy, sẽ so chênh mAP50 (clean − raw) với độ lệch chuẩn giữa 2 seed; giả thuyết cần kiểm: 11 ảnh `LEAK_TEST` trong `raw` thổi phồng mAP raw; test chỉ 100 ảnh nên nhiễu lớn.

## 6. Quyết định và ghi chú AI
(a) **Release** `clean_v1` (193 ảnh). Rủi ro còn lại: 13 ảnh cảnh báo chưa duyệt và 2 ảnh có thể bị loại oan do pHash 16; bản sau nên thêm kiểm tra phụ (SSIM/ORB) cho cặp pHash ≥ 14 trước khi loại. Điều kiện đổi quyết định: nếu hạ `conf` ≤ 0,7 (bắt thêm thiếu nhãn) thì thành **Hold** (≥ 13% > 10%); khi đó cần thêm ~6–35 lượt duyệt người (tuỳ conf) để kéo tỉ lệ cảnh báo xuống dưới 10% rồi mới Release.

(b) Có dùng AI (Claude Code):
- Prompt chính: "implement các check/autofix/gate theo docstring và test trong `tests/`, rồi điền báo cáo từ `submission/reports/`".
- Kiểm code AI: `pytest` (79 passed), chạy `make run`, đối chiếu `calibration_report.md`, `check_submission.py`, và mở ảnh xem các cặp near-dup.
- AI sai: AI chọn `phash_dist=16` vì calib báo P=1,00, nhưng khi mở ảnh thì 2/3 cặp ở khoảng cách 16 là ảnh khác nhau — số calib không đủ để tin.
