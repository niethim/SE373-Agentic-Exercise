# BÁO CÁO THỰC NGHIỆM CHALLENGE B: CONTEXT MANAGEMENT TRONG HỆ THỐNG AGENT

**Mục tiêu:** Kiểm soát và tối ưu không gian ngữ cảnh (Context Window) của Agent nhằm giảm thiểu chi phí token mà vẫn bảo toàn chính xác trạng thái nghiệp vụ và năng lực giải quyết công việc.  

---

## 1. TỔNG QUAN VÀ ĐẶT VẤN ĐỀ

Trong các kiến trúc Agent thực hiện tác vụ dài qua nhiều lượt tương tác (multi-turn workflows), không gian ngữ cảnh (Context Window) là bộ nhớ làm việc tạm thời (*working set*), không phải kho lưu trữ vô hạn. Khi agent liên tục thực thi công cụ đọc file hay chạy kiểm thử, context đối mặt với hiện tượng **Tool-Output Bloat**:
1. **Lãng phí chi phí và tăng độ trễ:** Input token tăng lũy tiến qua từng lượt gọi, làm tăng chi phí API và làm chậm thời gian phản hồi.
2. **Suy giảm chất lượng suy luận (Lost in the middle):** Quá nhiều log rác và dữ liệu trung gian khiến mô hình quên các ràng buộc ban đầu hoặc thử lại các phương án đã từng thất bại.

Challenge B giải quyết bài toán trên thông qua hai cơ chế bổ trợ hai chiều:
* **B1 — Compaction:** Rút gọn session dài tích lũy nhiều log thô thành một trạng thái cấu trúc (*Structured Checkpoint*), sau đó khởi động lại có kiểm soát (*Controlled Reboot*) để tiếp tục xử lý công việc.
* **B2 — Code Mode:** Ngăn chặn dữ liệu phình to ngay từ đầu bằng cách để môi trường thực thi (*Runtime*) đọc, lọc và tổng hợp hàng trăm file log bên ngoài context, chỉ đưa kết luận đã xử lý (*Findings*) vào context của mô hình.

---

## 2. CẤU TRÚC THƯ MỤC VÀ TRIỂN KHAI

Toàn bộ giải pháp được đóng gói độc lập trong thư mục `challeng_b/`:

```
challeng_b/
├── data/
│   ├── b1_auth_service/         # Mã nguồn service xác thực cho bài B1
│   │   ├── auth.ts              # Xử lý refreshToken (chứa lỗi race condition)
│   │   ├── session.ts           # Lưu trữ phiên làm việc
│   │   └── auth.test.ts         # Kiểm thử đồng thời (concurrency test)
│   └── b2_logs/                 # 100 file log backend cho bài B2
│       ├── service-001.log
│       └── ... service-100.log
├── checkpoints/
│   └── checkpoint.yaml          # Structured Checkpoint lưu trạng thái B1
├── traces/                      # Nhật ký thực thi sự kiện chi tiết (JSONL)
│   ├── trace_b1_compaction.jsonl
│   └── trace_b2_codemode.jsonl
├── generate_fixtures.py         # Bộ sinh dữ liệu mẫu chuẩn hóa cho B1 và B2
├── compaction.py                # Triển khai Selective Compaction & Controlled Reboot (B1)
├── codemode.py                  # Triển khai Runtime Log Processing ngoài context (B2)
├── run_all.py                   # Runner tự động chạy toàn bộ thử nghiệm
├── results.json                 # Kết quả đo lường và kiểm chứng định lượng
└── REPORT_CHALLENGE_B.md        # Báo cáo tổng kết kỹ thuật
```

### Chi tiết các thành phần chính:
* **Mục đích của các dòng log trong `data/b2_logs/`:**
  * Gồm 100 file log mô phỏng nhật ký của 100 worker/service trong hệ thống phân tán, chia làm 2 nhóm:
    1. *Nhóm log hoạt động bình thường (INFO/DEBUG):* Gồm các bản ghi sức khỏe dịch vụ, giải phóng bộ nhớ, cache hit. Nhóm này đóng vai trò là "nhiễu" thực tế để kiểm tra khả năng lọc sạch của code trong runtime.
    2. *Nhóm log lỗi (ERROR/FATAL/WARN):* Gồm đúng **1.130 lỗi thực tế** phân bổ ngẫu nhiên (`DatabaseConnectionTimeout`: 520, `NullPointerException`: 310, `TokenExpiredException`: 215, `DiskIOFailure`: 85).
  * *Ý nghĩa benchmark:* Tạo ra khối lượng dữ liệu thực tế lớn (**406.892 ký tự / ~116.254 tokens**) để đối đầu trực tiếp: Nếu dùng Native Tool Calling thì toàn bộ ~116k tokens log thô sẽ tràn vào LLM; trong khi dùng Code Mode thì chỉ có một bản JSON Findings nhỏ gọn được nạp vào context.
* **Vai trò của thư mục `traces/`:**
  * Lưu trữ vết thực thi từng bước theo định dạng JSONL chuẩn (tương tự observer/tracer của các hệ thống agent production).
  * Ghi lại chi tiết: thời điểm kích hoạt, snapshot prompt gửi mô hình, nội dung checkpoint, thời gian chạy runtime và dữ liệu đo lường token từ API để phục vụ thẩm định và tái lập kết quả (reproducibility).

---

## 3. THỰC NGHIỆM VÀ ĐỊNH LƯỢNG

Toàn bộ số liệu được đo lường thực tế khi chạy bộ điều phối `run_all.py` (ghi nhận trong `results.json`):

### Bảng Tổng hợp Kết quả Đo lường:

| Bài thử nghiệm | Input Tokens Ban đầu | Input Tokens Sau tối ưu | Tỷ lệ Tiết kiệm (%) | Thời gian Xử lý | Trạng thái |
|---|---|---|---|---|---|
| **B1: Compaction (Checkpoint)** | 62.852 tokens | **216 tokens** | **99,66%** | 11,91s | **SUCCESS** |
| **B2: Code Mode (100 log files)** | 116.254 tokens | **535 tokens** | **99,54%** | Runtime: 0,01s<br>LLM: 14,93s | **SUCCESS** |

### Phân tích số liệu:
1. **Compaction:** Một phiên làm việc 9 turns tích lũy 1.500 dòng log test failure cồng kềnh (62.852 tokens) được thu gọn về một Structured Checkpoint chỉ **216 tokens**, giảm **99,66%** dung lượng ngữ cảnh.
2. **Code Mode:** Quá trình quét và lọc 100 file log trong runtime chỉ mất **0,0108 giây**. Payload JSON kết luận nạp vào LLM chỉ tốn **535 tokens**, tiết kiệm **99,54%** chi phí đầu vào so với việc đọc trực tiếp 100 file log thô qua Native Tool Calling (~116k tokens).

---

## 4. KIỂM CHỨNG ĐỊNH TÍNH & HÀNH VI CỦA AGENT

Tối ưu hóa token chỉ thành công khi mô hình duy trì tính toàn vẹn về hành vi và đưa ra quyết định kỹ thuật chính xác.

### 4.1. Đánh giá 5 Tiêu chí Thành công của B1 (Compaction)

| Tiêu chí | Điều kiện kiểm chứng | Kết quả thực tế từ LLM sau Reboot | Đánh giá |
|---|---|---|---|
| **1. Nhớ đúng mục tiêu** | Tiếp tục sửa race condition của refresh token | *"Goal is to resolve the refresh-token race condition..."* | **PASS** |
| **2. Giữ nguyên ràng buộc** | Đảm bảo tính tương thích ngược của API | *"...while ensuring full API backward compatibility."* | **PASS** |
| **3. Nhớ đúng lỗi điều tra** | Xác định lỗi do xung đột đọc/ghi đồng thời | *"The issue is a logic race during concurrent read-modify-write cycles..."* | **PASS** |
| **4. Không lặp lại sai lầm** | Không đề xuất lại việc tăng TTL đã thất bại | *"Increasing token TTL failed [...] I will not repeat this approach."* | **PASS** |
| **5. Tiếp tục đúng bước kế tiếp** | Triển khai Locking/Mutex xung quanh refresh handler | *"Implement a locking mechanism (such as a distributed mutex or database-level row locking) to serialize refresh operations..."* | **PASS** |

### 4.2. Đánh giá 3 Tiêu chí Thành công của B2 (Code Mode)

| Tiêu chí | Điều kiện kiểm chứng | Kết quả thực nghiệm | Đánh giá |
|---|---|---|---|
| **1. Không rò rỉ log thô** | Raw log tuyệt đối không nằm trong prompt LLM | Prompt gửi đi chỉ chứa payload JSON Findings tổng hợp, không chứa các dòng log worker thô | **PASS** |
| **2. Thống kê chính xác 100%** | Kết quả đếm khớp chính xác với dữ liệu nguồn | Khớp hoàn toàn 1.130 lỗi: `DatabaseConnectionTimeout` (520), `NullPointerException` (310), `TokenExpiredException` (215), `DiskIOFailure` (85) | **PASS** |
| **3. Tiết kiệm token vượt trội** | Tỷ lệ tiết kiệm vượt ngưỡng 90% | Đạt **99,54%** mức giảm token đầu vào | **PASS** |

**Chẩn đoán nguyên nhân gốc rễ của mô hình dựa trên Findings:**
* *Nguyên nhân cốt lõi:* Cạn kiệt connection pool trong cơ sở dữ liệu khi hệ thống tải cao, thể hiện qua thời gian chờ vượt ngưỡng 30.000ms tại `DatabasePool.acquireConnection` (520 lần).
* *Giải pháp khắc phục:* Tăng kích thước kết nối của pool, tối ưu các câu truy vấn chậm và cấu hình cơ chế tự động mở rộng (auto-scaling) cho cơ sở dữ liệu.
