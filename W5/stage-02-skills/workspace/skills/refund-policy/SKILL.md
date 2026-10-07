---
name: refund-policy
description: Tra cứu và áp dụng chính sách hoàn tiền cho khách hàng dựa trên ngày mua hàng. Dùng khi người dùng hỏi về hoàn tiền, trả hàng, điều kiện hoàn tiền, phí hoàn tiền hoặc yêu cầu xét duyệt hoàn tiền.
---

# Chính sách hoàn tiền (Refund Policy)

Hướng dẫn kiểm tra điều kiện hoàn tiền và xác định chính sách áp dụng cho khách hàng dựa trên ngày mua hàng.

## Nguyên tắc cốt lõi
- **Không tự suy đoán**: Phải có đầy đủ 3 thông tin từ người dùng:
  1. Ngày mua sản phẩm.
  2. Ngày yêu cầu hoàn tiền.
  3. Trạng thái kích hoạt của sản phẩm (đã kích hoạt hay chưa kích hoạt).
  Nếu thiếu bất kỳ thông tin nào trong 3 thông tin trên, PHẢI hỏi lại người dùng để làm rõ trước khi đưa ra kết luận. KHÔNG tự giả định (ví dụ: không được tự cho rằng sản phẩm chưa kích hoạt).
- **Không cố định tên file**: Luôn dùng tool `list_files` để khám phá các file chính sách hiện có trong thư mục `data/policies/`.

## Các bước thực hiện

1. **Kiểm tra thông tin đầu vào**:
   - Kiểm tra xem người dùng đã cung cấp đủ: ngày mua, ngày yêu cầu hoàn tiền, và trạng thái kích hoạt chưa.
   - Nếu thiếu thông tin (ví dụ chưa nêu ngày yêu cầu hoặc chưa nêu trạng thái kích hoạt), dừng lại và phản hồi lịch sự hỏi người dùng cung cấp thông tin còn thiếu. Tuyệt đối chưa đưa ra kết luận hoàn tiền khi chưa đủ thông tin.

2. **Khám phá và đọc tài liệu chính sách**:
   - Dùng tool `list_files(path="data/policies")` để liệt kê danh sách các file chính sách đang có trong thư mục.
   - Dùng tool `read_file` để đọc nội dung từng file chính sách tìm được nhằm xác định phạm vi ngày mua áp dụng của từng phiên bản chính sách.

3. **Chọn chính sách và tính toán điều kiện**:
   - Căn cứ vào **ngày mua hàng**, xác định chính sách nào có hiệu lực cho ngày mua đó:
     - Nếu ngày mua trước ngày 2026-10-01 (tức từ 2026-09-30 trở về trước): áp dụng chính sách trước tháng 10.
     - Nếu ngày mua từ ngày 2026-10-01 trở đi (bao gồm cả ngày 2026-10-01): áp dụng chính sách từ tháng 10.
   - Tính số ngày đã qua: Số ngày = chênh lệch ngày lịch giữa ngày yêu cầu hoàn và ngày mua (ví dụ: mua 28/09/2026, yêu cầu 06/10/2026 -> 8 ngày; mua 02/10/2026, yêu cầu 12/10/2026 -> 10 ngày). Bằng đúng giới hạn vẫn đủ điều kiện về thời gian. Sử dụng ngày yêu cầu trong câu hỏi của người dùng, không dùng ngày hiện tại của hệ thống.
   - Xét điều kiện:
     - Nếu sản phẩm đã kích hoạt: Không hoàn tiền trong mọi trường hợp.
     - Nếu sản phẩm chưa kích hoạt:
       + Chính sách trước tháng 10: Giới hạn trong 7 ngày kể từ ngày mua; phí hoàn tiền là 10% giá trị đơn hàng.
       + Chính sách từ tháng 10: Giới hạn trong 14 ngày kể từ ngày mua; không thu phí hoàn tiền (0%).

4. **Đọc template và định dạng câu trả lời**:
   - Đọc template tham khảo tại `skills/refund-policy/references/answer-template.md` bằng tool `read_file`.
   - Trình bày câu trả lời cho người dùng theo đúng cấu trúc trong template:
     + Chính sách áp dụng.
     + Số ngày đã qua.
     + Kết luận: Đủ điều kiện hay Không đủ điều kiện hoàn tiền.
     + Phí hoàn tiền (nếu đủ điều kiện).
     + Căn cứ tài liệu: Đường dẫn file tài liệu cụ thể đã sử dụng trong `data/policies/`.
