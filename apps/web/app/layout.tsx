import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "ReupStudio",
  description:
    "Tự động lấy video Trung Quốc, dịch sang tiếng Việt và đăng lên nền tảng video ngắn",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      {/*
        `suppressHydrationWarning` cho RIÊNG thẻ body: tiện ích trình duyệt hay
        gắn thêm thuộc tính vào đây TRƯỚC khi React chạy, và React coi đó là
        server với client không khớp.

        Gặp thật ngày 16.08.2026: một tiện ích gắn `bis_register="..."` vào
        body — giải mã ra `{"master":true,"extensionId":"eppiocemhmnlbhjplc..."}`,
        đúng tiện ích đã làm hỏng `fetch` ở `lib/api.ts`. Màn hình đỏ chỉ vào
        mã của mình trong khi mình không hề sinh ra thuộc tính đó.

        Chỉ tắt cảnh báo ở ĐÚNG một thẻ. Lệch thật ở bên trong cây vẫn báo bình
        thường — tắt rộng hơn là tự bịt mắt.
      */}
      <body suppressHydrationWarning>
        <Providers>
          <div className="flex flex-col h-screen overflow-hidden">
            <Topbar />
            <div className="flex flex-1 overflow-hidden">
              <Sidebar />
              <main className="flex-1 overflow-y-auto px-6 py-5">{children}</main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
