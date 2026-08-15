"""Cấu hình chung cho test.

Chặn việc đọc cấu hình từ database: test phải cho cùng kết quả trên mọi máy,
mà database của mỗi người một khác. Không có dòng này thì các test khoá hành vi
"không cấu hình gì thì dùng mặc định" sẽ đọc phải cấu hình thật của người chạy.
"""

from __future__ import annotations

import os

os.environ["REUP_BO_QUA_CAU_HINH_DB"] = "1"
