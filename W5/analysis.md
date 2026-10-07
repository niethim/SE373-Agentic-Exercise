# BÁO CÁO PHÂN TÍCH THỰC NGHIỆM: BLOCK 1 - TRA CỨU CHÍNH SÁCH ĐÚNG PHIÊN BẢN

- **Môn học**: Agentic AI Engineering (SE373)
- **Bài thực hành**: W5 - Block 1: Tra cứu chính sách đúng phiên bản (Tool Use & Skill Use)
- **Môi trường**: Linux (Kernel 6.x), Python 3.12 (uv), LangChain 1.4+, LangGraph 1.2+

---

## 1. Tổng quan Kiến trúc & Giải pháp

Trong bài thực hành Block 1, project ban đầu chỉ hỗ trợ thao tác đọc/ghi file đơn lẻ (`read_file`, `write_file`) mà chưa có cơ chế khám phá thư mục và chưa có tri thức nghiệp vụ về chính sách hoàn tiền theo thời gian. Chúng tôi đã xây dựng giải pháp theo 2 thành phần chính:

1. **Tool `list_files(path: str)` (Stage 01 & Stage 02)**:
   - Cung cấp khả năng quan sát hệ thống file động (environmental sensing/discovery).
   - Liệt kê các mục trực tiếp (không duyệt đệ quy), phân loại `file` hoặc `directory`, sắp xếp theo tên để đảm bảo tính ổn định (deterministic).
   - Tái sử dụng cơ chế bảo mật nghiêm ngặt `_resolve`: ngăn chặn triệt để path traversal (`..`), đường dẫn tuyệt đối, hoặc symlink trỏ ra ngoài workspace.
   - Xử lý lỗi có cấu trúc: trả mã lỗi `NOT_A_DIRECTORY` khi trỏ vào file, `FILE_NOT_FOUND` khi đường dẫn không tồn tại, `PATH_OUTSIDE_WORKSPACE` khi vượt ra ngoài workspace.

2. **Skill `refund-policy` (Stage 02)**:
   - Thư mục skill: `workspace/skills/refund-policy/` gồm `SKILL.md` và `references/answer-template.md`.
   - **Frontmatter**: Khai báo `name: refund-policy` và `description` rõ ràng để model nhận diện trigger khi người dùng hỏi về hoàn tiền / trả hàng.
   - **Nguyên tắc cốt lõi (Guardrail)**: Ngăn chặn tự suy đoán; yêu cầu đủ 3 thông tin đầu vào (ngày mua, ngày yêu cầu hoàn, trạng thái kích hoạt). Nếu thiếu thông tin, bắt buộc hỏi lại người dùng trước khi kết luận.
   - **Quy trình thực thi**:
     1. Dùng `list_files(path="data/policies")` để quét danh sách file chính sách hiện có mà không bị phụ thuộc vào tên file cố định.
     2. Đọc nội dung file chính sách bằng `read_file` để xác định khoảng ngày hiệu lực.
     3. Tính số ngày chênh lệch ngày lịch giữa ngày yêu cầu hoàn và ngày mua (dùng ngày trong câu hỏi, không dùng ngày của máy).
     4. Áp dụng chính sách tương ứng theo ngày mua:
        - Mua trước 2026-10-01: Tối đa 7 ngày, phí 10%, chưa kích hoạt.
        - Mua từ 2026-10-01 trở đi: Tối đa 14 ngày, phí 0%, chưa kích hoạt.
     5. Đọc template `skills/refund-policy/references/answer-template.md` và xuất kết quả theo định dạng chuẩn hóa.

---

## 2. Kết quả kiểm tra Tool trực tiếp (Direct Tool Verification)

Tool `list_files` được kiểm tra độc lập trên 4 kịch bản đại diện theo đúng yêu cầu đề bài:

| STT | Kịch bản kiểm tra | Đường dẫn đầu vào (`path`) | Kết quả trả về | Mã lỗi (`code`) / Nội dung | Đánh giá |
|:---:|---|---|:---:|---|:---:|
| 1 | Thư mục hợp lệ | `data/policies` | `ok: true` | Trả về danh sách entries gồm các file chính sách (`type: file`) | **ĐẠT** |
| 2 | Đường dẫn là file | `data/weekly_notes.md` | `ok: false` | `NOT_A_DIRECTORY` ("Đây là file, không phải thư mục: data/weekly_notes.md") | **ĐẠT** |
| 3 | Đường dẫn không tồn tại | `data/khong-ton-tai` | `ok: false` | `FILE_NOT_FOUND` ("Không tìm thấy thư mục: data/khong-ton-tai") | **ĐẠT** |
| 4 | Đường dẫn ngoài workspace | `../secret.txt` | `ok: false` | `PATH_OUTSIDE_WORKSPACE` ("Đường dẫn thoát ra ngoài workspace: ../secret.txt") | **ĐẠT** |

**Nhận xét**: Cả 3 trường hợp bất thường (2, 3, 4) đều bị chặn an toàn và trả lỗi có cấu trúc rõ ràng, không làm crash hệ thống và không trả danh sách rỗng giả mạo.

---

## 3. Kết quả các Trường hợp Thực nghiệm (End-to-End Cases)

### 3.1. Trường hợp A: Mua trước ngày đổi chính sách
- **Câu hỏi của người dùng**:
  > *"Tôi mua ngày 28/09/2026, yêu cầu hoàn ngày 06/10/2026, chưa kích hoạt. Tôi có được hoàn không?"*
- **File trace**: `traces/trace_case_a.jsonl` (tương ứng `20261007-153814_case-a-c_turn01_1325e14c.jsonl`)
- **Số lần gọi model / tool**: 5 model calls, 4 tool calls (20 events).
- **Hành vi thực tế của Agent**:
  1. Đọc metadata skill từ catalog và gọi `read_file` đọc `skills/refund-policy/SKILL.md`.
  2. Gọi `list_files("data/policies")` để lấy danh sách file.
  3. Xác định ngày mua `28/09/2026` < `2026-10-01` nên gọi `read_file` đọc `data/policies/policy-before-oct.md`.
  4. Đọc `skills/refund-policy/references/answer-template.md`.
  5. Tính toán: $06/10/2026 - 28/09/2026 = 8\text{ ngày} > 7\text{ ngày}$ (giới hạn cho phép).
- **Câu trả lời của Agent**:
  ```markdown
  # Kết quả xét duyệt hoàn tiền

  - **Chính sách áp dụng**: Chính sách hoàn tiền trước tháng 10
  - **Số ngày đã qua**: 8 ngày (Giới hạn cho phép: 7 ngày)
  - **Trạng thái sản phẩm**: Chưa kích hoạt
  - **Kết luận**: Không đủ điều kiện hoàn tiền - Đã vượt quá thời hạn 7 ngày theo chính sách áp dụng.
  - **Phí hoàn tiền**: N/A
  - **Căn cứ tài liệu**: `data/policies/policy-before-oct.md`
  ```
- **Kết luận**: Chọn đúng chính sách cũ, tính đúng 8 ngày, kết luận chính xác không đủ điều kiện, dẫn đúng tài liệu căn cứ.

---

### 3.2. Trường hợp B (Sau khi đổi tên file chính sách): Mua từ ngày đổi chính sách
- **Thiết lập thử nghiệm**:
  - Đổi tên file trong `data/policies/`:
    + `policy-before-oct.md` $\rightarrow$ `quy-dinh-hoan-tien-cu.md`
    + `policy-from-oct.md` $\rightarrow$ `quy-dinh-hoan-tien-moi.md`
  - Mở cuộc trò chuyện hoàn toàn mới (fresh conversation), không lưu ngữ cảnh từ Trường hợp A.
- **Câu hỏi của người dùng**:
  > *"Tôi mua ngày 02/10/2026, yêu cầu hoàn ngày 12/10/2026, chưa kích hoạt. Tôi có được hoàn không?"*
- **File trace**: `traces/trace_case_b_renamed.jsonl` (tương ứng `20261007-154116_case-b-7_turn01_e26954cb.jsonl`)
- **Số lần gọi model / tool**: 6 model calls, 5 tool calls (24 events).
- **Hành vi thực tế của Agent**:
  1. Đọc `skills/refund-policy/SKILL.md`.
  2. Gọi `list_files("data/policies")` $\rightarrow$ nhận danh sách chứa các file đã đổi tên: `quy-dinh-hoan-tien-cu.md`, `quy-dinh-hoan-tien-moi.md`.
  3. Ngày mua `02/10/2026` $\ge$ `2026-10-01` $\rightarrow$ Agent tự động chọn và gọi `read_file` đọc file mới `data/policies/quy-dinh-hoan-tien-moi.md`.
  4. Đọc `skills/refund-policy/references/answer-template.md`.
  5. Tính toán: $12/10/2026 - 02/10/2026 = 10\text{ ngày} \le 14\text{ ngày}$, sản phẩm chưa kích hoạt $\rightarrow$ Đủ điều kiện, không mất phí.
- **Câu trả lời của Agent**:
  ```markdown
  # Kết quả xét duyệt hoàn tiền

  - **Chính sách áp dụng**: Chính sách hoàn tiền từ tháng 10
  - **Số ngày đã qua**: 10 ngày (Giới hạn cho phép: 14 ngày)
  - **Trạng thái sản phẩm**: Chưa kích hoạt
  - **Kết luận**: Đủ điều kiện hoàn tiền - Sản phẩm chưa kích hoạt và yêu cầu trong thời hạn cho phép.
  - **Phí hoàn tiền**: Không thu phí (0%)
  - **Căn cứ tài liệu**: `data/policies/quy-dinh-hoan-tien-moi.md`
  ```
- **Kết luận**: Agent tự động phát hiện được file bị đổi tên nhờ `list_files`, áp dụng chính xác phiên bản chính sách mới, tính đúng 10 ngày, kết luận đủ điều kiện với 0% phí, và trích dẫn đúng đường dẫn file mới.

---

### 3.3. Trường hợp Thiếu thông tin
- **Câu hỏi của người dùng**:
  > *"Tôi mua ngày 02/10/2026, muốn hoàn ngày 12/10/2026."*
  *(Lưu ý: Không đề cập trạng thái sản phẩm đã kích hoạt hay chưa).*
- **File trace**: `traces/trace_case_missing_info.jsonl` (tương ứng `20261007-154229_case-mis_turn01_a9ccc50c.jsonl`)
- **Số lần gọi model / tool**: 2 model calls, 1 tool call (8 events).
- **Hành vi thực tế của Agent**:
  1. Đọc `skills/refund-policy/SKILL.md`.
  2. Đối chiếu quy định trong skill: *"Phải có đầy đủ 3 thông tin từ người dùng: 1. Ngày mua, 2. Ngày yêu cầu, 3. Trạng thái kích hoạt... Nếu thiếu... PHẢI hỏi lại... KHÔNG tự giả định"*.
  3. Phát hiện thiếu thông tin kích hoạt $\rightarrow$ Agent dừng quy trình xét duyệt, không tự suy đoán là "chưa kích hoạt".
- **Câu trả lời của Agent**:
  > *"Để có thể kiểm tra chính sách hoàn tiền cho bạn, tôi cần biết thêm một thông tin quan trọng: **Sản phẩm bạn đã mua đã được kích hoạt hay chưa?**"*
  > *"Vui lòng cung cấp thêm thông tin này để tôi có thể hỗ trợ bạn chính xác nhất."*
- **Kết luận**: Hoàn toàn tuân thủ quy tắc guardrail của skill; không bị ảo giác, không vội vàng kết luận mà chủ động đặt câu hỏi làm rõ.

---

## 4. Vị trí Bằng chứng trong Trace (Trace Evidence Mapping)

Chi tiết ánh xạ các mốc sự kiện quan trọng trong các file trace:

### Bảng đối chiếu sự kiện trong Trace:

| Trường hợp | Sequence | Loại sự kiện (`type`) | Tool / Thao tác | Arguments / Kết quả chi tiết | Ý nghĩa / Bằng chứng |
|---|:---:|---|---|---|---|
| **Case A** | Seq 4 - 5 | `tool_started` / `tool_finished` | `read_file` | `path: "skills/refund-policy/SKILL.md"` | Agent tải nội dung skill vào ngữ cảnh |
| **Case A** | Seq 8 - 9 | `tool_started` / `tool_finished` | `list_files` | `path: "data/policies"` $\rightarrow$ trả về `policy-before-oct.md`, `policy-from-oct.md` | Agent chủ động khám phá danh mục chính sách |
| **Case A** | Seq 12 - 13 | `tool_started` / `tool_finished` | `read_file` | `path: "data/policies/policy-before-oct.md"` | Agent chọn đúng chính sách áp dụng trước tháng 10 |
| **Case A** | Seq 16 - 17 | `tool_started` / `tool_finished` | `read_file` | `path: "skills/refund-policy/references/answer-template.md"` | Agent tải template câu trả lời chuẩn |
| **Case A** | Seq 20 | `run_completed` | Hoàn tất | Trả lời: 8 ngày, không đủ điều kiện, dẫn `policy-before-oct.md` | Hoàn thành turn với đầy đủ kết luận chính xác |
| **Case B (Đổi tên)** | Seq 4 - 9 | `tool_started` / `tool_finished` | `list_files` + `read_file` | Nạp `skills/refund-policy/SKILL.md` | Tải skill trong conversation mới |
| **Case B (Đổi tên)** | Seq 12 - 13 | `tool_started` / `tool_finished` | `list_files` | `path: "data/policies"` $\rightarrow$ trả về `quy-dinh-hoan-tien-cu.md`, `quy-dinh-hoan-tien-moi.md` | **Bằng chứng cốt lõi**: Agent phát hiện 2 file đã đổi tên |
| **Case B (Đổi tên)** | Seq 16 - 17 | `tool_started` / `tool_finished` | `read_file` | `path: "data/policies/quy-dinh-hoan-tien-moi.md"` | **Bằng chứng cốt lõi**: Agent đọc file đã đổi tên tương ứng |
| **Case B (Đổi tên)** | Seq 20 - 21 | `tool_started` / `tool_finished` | `read_file` | `path: "skills/refund-policy/references/answer-template.md"` | Tải template định dạng |
| **Case B (Đổi tên)** | Seq 24 | `run_completed` | Hoàn tất | Trả lời: 10 ngày, đủ điều kiện, 0% phí, dẫn `quy-dinh-hoan-tien-moi.md` | Dẫn chứng đúng file mới, không dùng file cũ |
| **Thiếu thông tin** | Seq 4 - 5 | `tool_started` / `tool_finished` | `read_file` | `path: "skills/refund-policy/SKILL.md"` | Đọc quy tắc bắt buộc 3 thông tin |
| **Thiếu thông tin** | Seq 8 | `run_completed` | Hoàn tất | Hỏi lại trạng thái kích hoạt, dừng gọi tool tiếp | **Bằng chứng cốt lõi**: Không tự giả định, tuân thủ guardrail |

---

## 5. Trả lời các Câu hỏi cuối bài

### Câu 1: Vì sao cần tool để tìm file và skill để hướng dẫn chọn chính sách?

1. **Vì sao cần Tool để tìm file (`list_files`)?**
   - **Khả năng quan sát môi trường động (Environmental Sensing / Runtime Discovery)**:
     Trong thực tế, hệ thống tập tin luôn biến động (tên file thay đổi theo phiên bản, tài liệu mới được bổ sung, định dạng cập nhật). Nếu chỉ trang bị `read_file`, agent bắt buộc phải biết trước đường dẫn file chính xác đến từng ký tự. Nếu không có "cặp mắt" `list_files`, agent hoàn toàn "mù" trước cấu trúc thư mục hiện hành và không thể tương tác khi môi trường thay đổi.
   - **Độc lập với tên file (Decoupling from Hardcoded Paths)**:
     Tool `list_files` phân tách logic nghiệp vụ khỏi tên file vật lý. Agent có thể truy vấn thư mục tại thời điểm thực thi (runtime) để lấy danh sách file thực tế, từ đó đọc và chọn lựa file phù hợp mà không cần sửa code hay sửa system prompt mỗi khi file đổi tên.

2. **Vì sao cần Skill để hướng dẫn chọn chính sách (`refund-policy`)?**
   - **Hướng dẫn quy trình nghiệp vụ chuyên biệt (Domain-Specific SOP)**:
     Tool chỉ cung cấp khả năng kỹ thuật (liệt kê, đọc, ghi file), nhưng tool không thể biết *khi nào* và *theo quy tắc nào* để ra quyết định nghiệp vụ. Skill đóng vai trò là một quy trình thao tác chuẩn (SOP) chỉ dẫn:
     - Cách chọn chính sách dựa trên **ngày mua hàng** (chứ không phải ngày yêu cầu hoàn tiền hay ngày hiện tại).
     - Quy tắc tính số ngày lịch (lấy ngày trong câu hỏi, bao gồm cả ngày mốc).
     - Yêu cầu kiểm soát dữ liệu: bắt buộc đủ 3 thông tin (ngày mua, ngày hoàn, kích hoạt) trước khi kết luận.
   - **Tối ưu ngữ cảnh qua cơ chế Lazy-loading (Progressive Disclosure)**:
     Nếu nhét toàn bộ hướng dẫn nghiệp vụ của hàng chục phòng ban/chính sách vào System Prompt, context window sẽ bị tràn, chi phí token tăng vọt và model dễ bị nhiễu. Skill catalog chỉ đưa metadata tóm tắt vào System Prompt ban đầu; chỉ khi người dùng hỏi đúng nghiệp vụ hoàn tiền, model mới tự động gọi `read_file` nạp nội dung chi tiết của `SKILL.md` và `references/`.

---

### Câu 2: Nếu agent chưa có tool tìm file, việc sửa prompt có giải quyết được yêu cầu đổi tên file không? Giải thích.

**Trả lời**: **KHÔNG THỂ GIẢI QUYẾT ĐƯỢC.** Việc chỉ sửa prompt không thể giải quyết được bài toán đổi tên file trong môi trường thực tế vì những lý do sau:

1. **Bản chất tĩnh của Prompt (Static Nature vs. Dynamic Reality)**:
   - System prompt là cấu hình tĩnh được thiết lập trước khi cuộc trò chuyện diễn ra. Nếu không có tool liệt kê thư mục, prompt buộc phải ghi cứng (hardcode) tên file mà agent cần đọc (ví dụ: `Đọc file data/policies/policy-before-oct.md`).
   - Khi có sự thay đổi trên đĩa (ví dụ: đổi thành `quy-dinh-hoan-tien-cu.md` hoặc một mã định danh ngẫu nhiên do hệ thống sinh ra), prompt tĩnh sẽ lập tức trở nên lỗi thời. Agent khi gọi `read_file` với đường dẫn cũ sẽ luôn nhận lỗi `FILE_NOT_FOUND`.

2. **Prompt không thể dự đoán tương lai (Lack of Clairvoyance)**:
   - Nếu lập luận rằng *"ta có thể sửa prompt để cập nhật tên file mới"*, thì đây chỉ là giải pháp tình thế mang tính thủ công và đối phó cho từng trường hợp cụ thể, chứ không phải giải quyết bài toán tự động thích ứng.
   - Trong một hệ thống thực tế với hàng nghìn file tài liệu được cập nhật liên tục bởi các bộ phận khác nhau, việc con người phải can thiệp sửa prompt mỗi lần có file đổi tên là bất khả thi và phá vỡ tính tự chủ (autonomy) của Agent.

3. **Gia tăng nguy cơ Ảo giác (Hallucination) và Thất bại hàng loạt**:
   - Khi không có tool tìm file và không biết tên file mới, agent sẽ rơi vào 2 trạng thái nguy hiểm:
     1. Liên tục đoán mò tên file (blind guessing) dẫn đến cạn kiệt giới hạn `tool_call_limit` hoặc `model_call_limit`.
     2. Tự suy diễn và bịa đặt nội dung chính sách từ kiến thức huấn luyện sẵn có trong trọng số (parametric memory) thay vì đọc từ nguồn dữ liệu thực tế (grounding data), dẫn đến đưa ra kết luận hoàn tiền sai lệch nghiêm trọng cho khách hàng.

$\implies$ **Kết luận**: Tool `list_files` là năng lực quan sát tối thiểu bắt buộc để agent tự thích ứng với biến động môi trường; Prompt engineering thuần túy không thể thay thế được khả năng tương tác với hệ thống tập tin.
