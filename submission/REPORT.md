# Báo cáo Day 09 — Nguyen Van Nhat, 2A202603273

## 1. Kết luận trước
Pipeline kết luận **Release** (`08_summary.json`). **224 ảnh vào → 202 ảnh ra** `export/clean_v1` (22 ảnh bị loại ở bước 1).
Sau autofix + 80 ảnh người duyệt, danh sách v3 còn **0 lỗi bắt buộc**; còn **16/202 ảnh (7,92%)** có cảnh báo chưa duyệt, dưới ngưỡng Hold 10%.

## 2. Lỗi và phân việc
Theo `02_error_list_v1` (mẫu số: 224 ảnh quét; 58 dòng lỗi bắt buộc, 112 dòng cảnh báo; số = dòng (ảnh)).

| Mã lỗi | Số dòng (ảnh) | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR | 8 (8) / 4 (4) | máy (loại ảnh) | trùng byte / pHash ≤ 12, giữ ảnh gốc |
| LEAK_TEST | 5 (5) | máy (loại ảnh) | trùng ảnh kho test/val → giữ lại là rò rỉ đánh giá |
| BAD_SIZE / CORRUPT_IMAGE | 3 (3) / 2 (2) | máy (loại ảnh) | cạnh < 250px / không mở được, không có gì để sửa |
| BAD_CLASS_ID, BAD_FORMAT, BOX_ZERO, DUP_BOX | 6 / 3 / 4 / 7 | máy (`drop_line`, 20 dòng) | dòng hỏng theo quy tắc → xoá dòng rồi đẩy ảnh vào hàng đợi (`FIXED_DROP_LINE`) |
| BOX_OUT_OF_IMAGE | 8 (8) | máy (`clip_box`, 8 dòng) | tràn mép: kẹp về [0,1] là an toàn |
| BAD_CLASS_NAME | 2 (data.yaml) | máy (`rename_classes`) | `Person`/`Bus` → `person`/`bus`, chỉ khác hoa/thường |
| MISSING_LABEL_FILE | 6 (6) | **người** (`NEEDS_LABEL`) | máy không biết ảnh có vật gì, không bịa nhãn |
| POSSIBLE_WRONG_CLASS / MISSING / FALSE_POS / LOOSE_BOX | 14 / 32 / 29 / 12 | **người** | ý nghĩa nhãn; model lớn chỉ là ý kiến thứ hai |
| EMPTY_LABEL, BOX_TINY, BOX_HUGE, CLASS_RARE | 12 / 6 / 3 / 4 | người (nếu còn ngân sách) | cảnh báo quy tắc dự án, không chắc là sai |

`05_review_queue.csv` (102 ảnh) xếp theo tổng trọng số mã lỗi: đầu hàng là `img_0020` (11,52 = FIXED_DROP_LINE + MISSING + WRONG_CLASS) rồi 6 ảnh `NEEDS_LABEL` (10) — ảnh thiếu nhãn phải xử lý trước, nếu không gate sẽ Rework. Tiếp theo là ảnh có lỗi ngữ nghĩa trọng số cao (WRONG_CLASS 3, MISSING/FALSE_POS 2).
Với ngân sách 80 ảnh, người duyệt **68 ảnh có lỗi ngữ nghĩa, 77/81 cờ ngữ nghĩa** trong hàng đợi (đủ 14 WRONG_CLASS, 32 MISSING, 12 LOOSE_BOX; 19/23 FALSE_POS). 22 ảnh cuối hàng (ưu tiên ≤ 2,0: EMPTY_LABEL 6, FALSE_POS 4, FIXED_CLIP_BOX 4, BOX_TINY 3, BOX_HUGE 3, FIXED_DROP_LINE 2) không được xem.

## 3. Calibration (2 ngưỡng)
Đo trên `data/calib` (lỗi chèn có đáp án), `calibration_report.md`.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | NEAR: 1,00/0,50 → 1,00/0,67 (EXACT giữ 1,00/1,00) | calib cho 16 tốt hơn (R 0,83) nhưng trên lô thật 16 báo nhầm hàng loạt (xem dưới); 12 nằm giữa khoảng trống 10–16 của lô thật |
| `second_opinion.conf` | 0.25 | **0.8** | WRONG_CLASS 0,56/0,83 → 1,00/0,83; MISSING 0,50/1,00 → 0,67/0,75 | người duyệt chỉ có 80 ảnh nên ưu tiên precision; đổi lại mất 2/8 MISSING, LOOSE_BOX 0,29/0,40 → 0,50/0,20 |

**Chọn 12 bằng phân bố khoảng cách thật:** tính pHash giữa mọi ảnh raw với nhau và với kho test/val, mở ảnh các cặp ở ranh giới:

| khoảng cách | 0–2 | 6 | 10 | 11–15 | 16 | 18 | 20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| số cặp | 14 | 2 | 1 | **0** | 9 | 51 | 209 |
| mở ảnh xem | trùng thật | trùng thật (đổi màu; `img_0101`↔`test_039` rò rỉ có viền đen) | trùng thật (`img_0186`↔`img_0061`, đổi sáng) | — | 8 khác nhau, 1 lật gương | ảnh khác | ảnh khác |

Trùng thật đều ≤ 10, báo nhầm bắt đầu từ 16 → mọi ngưỡng 10–14 cho kết quả **y hệt** trên lô thật (đã chạy lại: 202 ảnh, `01`/`02`/`05`/`06`/`07` không đổi so với 10) và trên calib (4–14 cùng NEAR 1,00/0,67). 10 nằm sát một cặp trùng thật (`img_0186` đúng 10), 14 sát vùng báo nhầm (16), nên chọn **12** ở giữa, chừa biên 2 mỗi phía.

**Chỗ calibration đánh lừa (phash):** ban đầu mình chọn 16 vì calib báo NEAR 1,00/0,83. Trên lô thật, 16 loại **31** ảnh, 12 chỉ loại **22**: 9 ảnh chênh lệch đều nằm đúng khoảng cách 16. Mở xem từng cặp: 6 "LEAK_TEST" (`img_0013`↔`test_087` bàn máy tính vs bóng chày, `img_0021`↔`test_048` người đứng vs xe buýt, `img_0115`↔`test_088`…) và 2 "NEAR" (`img_0011`↔`img_0008` tennis vs trượt tuyết, `img_0177`↔`img_0113`) **là ảnh hoàn toàn khác nhau**; chỉ `img_0084`↔`img_0074` (lật gương) là trùng thật. Tức ở khoảng cách 16 precision thật là **1/9**, trái với 1,00 trên calib (chỉ 6 ảnh near-dup, không có ảnh "khác nhưng pHash gần"). Đổi lại, phash 12 bỏ lọt 1 ảnh trùng lật gương (`img_0084`). Lưu ý thêm: `phash_dist` dùng chung cho kiểm rò rỉ test, nên ngưỡng quá lỏng còn làm số LEAK_TEST phình (11 → thật ra 5).

**Kết luận nhạy với `conf`:** chạy lại pipeline (budget 80, phash 10–12 cho cùng kết quả) chỉ đổi `conf`: 0,25 → 58/202 (28,7%), 0,5 → 44/202 (21,8%), 0,6 → 38/202 (18,8%), 0,7 → 29/202 (14,4%) — **đều Hold**; chỉ 0,8 → 16/202 (7,9%) mới Release. Mình chọn 0,8 vì đó là giá trị tốt nhất trên calib (tổng F1 4 mã second-opinion: 2,39 ở 0,8 so với 2,18 ở 0,7 và 2,12 ở 0,6), không phải để qua cổng; nhưng Release đạt được **một phần nhờ bớt cờ** (MISSING recall 1,00 → 0,75), tức một số thiếu nhãn không được báo chứ không phải đã được sửa.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` → **REWORK** ("Còn 6 lỗi bắt buộc trên 6 ảnh/tệp (mã: MISSING_LABEL_FILE)", thêm 85/202 = 42,08% ảnh còn cảnh báo), **mã thoát 20**, log "Bước 5/5 KHÔNG xuất", và `work/exp_nb` **không tồn tại**. Gate chặn đúng.

(b) Điểm mù có bằng chứng:
1. **Box lỏng nhẹ:** `POSSIBLE_LOOSE_BOX` recall chỉ **0,20 (1/5)** trên calib ở conf 0,8 — box lệch nhưng IoU vẫn ≥ 0,5 thì lọt hoàn toàn.
2. **Nhầm lớp mà model cũng nhầm / không tự tin:** WRONG_CLASS recall 0,83 (1/6 lọt ở mọi conf); trên lô thật v3 còn `img_0078` "truck nhưng model nói car (conf 0,83)" — truck/car dễ lẫn, model không phải đáp án.
3. **Ảnh trùng biến đổi mạnh:** ở phash 12, ảnh lật gương `img_0084` (khoảng cách 16 tới `img_0074`) lọt vào dataset; nới lên 16 để bắt nó thì báo nhầm 8 ảnh khác. pHash không tách được "biến đổi mạnh" với "ảnh khác".
4. **FALSE_POS báo nhầm nhiều** (P 0,31 trên calib): 4 ảnh FALSE_POS cuối hàng đợi không được người xem, v3 còn 13 dòng.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Chưa chạy**: chưa có GPU/Colab trong thời gian làm bài (`submission/results/` trống). Nếu chạy, sẽ so chênh mAP50 (clean − raw) với độ lệch chuẩn giữa 2 seed; giả thuyết cần kiểm: 5 ảnh `LEAK_TEST` trong `raw` thổi phồng mAP raw; test chỉ 100 ảnh nên nhiễu lớn.

## 6. Quyết định và ghi chú AI
(a) **Release** `clean_v1` (202 ảnh). Rủi ro còn lại: 16 ảnh cảnh báo chưa duyệt và 1 ảnh trùng lật gương (`img_0084`) còn trong dataset; bản sau nên thêm kiểm tra phụ (SSIM/ORB hoặc pHash của ảnh lật) cho cặp pHash 11–16 thay vì chỉ dùng một ngưỡng. Điều kiện đổi quyết định: hạ `conf` ≤ 0,7 thì thành **Hold** (≥ 14,4% > 10%); khi đó cần thêm ~9–38 lượt duyệt người (tuỳ conf) để kéo tỉ lệ cảnh báo xuống dưới 10% rồi mới Release.

(b) Có dùng AI (Claude Code):
- Prompt chính: "implement các check/autofix/gate theo docstring và test trong `tests/`, rồi điền báo cáo từ `submission/reports/`".
- Kiểm code AI: `pytest` (79 passed), chạy `make run`, đối chiếu `calibration_report.md`, `check_submission.py`, và mở ảnh xem các cặp bị coi là trùng/rò rỉ.
- AI sai: AI chọn `phash_dist=16` vì calib báo P=1,00, nhưng mở ảnh thì 8/9 cặp ở khoảng cách 16 là ảnh khác nhau — đã đổi sang 12 dựa trên phân bố khoảng cách thật.
