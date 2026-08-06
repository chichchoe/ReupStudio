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
      <body>
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
