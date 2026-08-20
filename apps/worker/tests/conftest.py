"""Cấu hình chung cho test.

Hai thứ bị chặn ở đây, cả hai vì cùng một lý do: test không được phụ thuộc
vào — và không được làm bẩn — máy của người chạy.

1. Đọc cấu hình từ database: test phải cho cùng kết quả trên mọi máy,
mà database của mỗi người một khác. Không có dòng này thì các test khoá hành vi
"không cấu hình gì thì dùng mặc định" sẽ đọc phải cấu hình thật của người chạy.

2. Ghi vào thư mục media thật. ``paths.py`` cố ý TẠO thư mục ngay khi được
   hỏi đường dẫn (``_ensure``), nên chỉ cần một test gọi ``giong_dir()`` là
   ``media/giong/`` mọc thêm một thư mục mồ côi — mỗi lần chạy test một cái.
   Quan sát ngày 2026-08-21: 16 thư mục rác tích lại trước khi có dòng này.
"""

from __future__ import annotations

import os
import tempfile

os.environ["REUP_BO_QUA_CAU_HINH_DB"] = "1"

#: Trỏ media sang thư mục tạm TRƯỚC khi bất kỳ module nào đọc ``MEDIA_ROOT``.
#: Đặt ở conftest cấp gói chứ không từng test: chỉ cần một test quên là rác
#: lại rơi vào media thật, mà kiểu hỏng đó không ai để ý cho tới khi thư mục
#: phình lên.
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="reup-test-media-")
