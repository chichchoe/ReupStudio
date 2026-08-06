import type { Config } from "tailwindcss";

/** Bảng màu lấy đúng từ mockup — xem docs/thiet-ke-web-app.md */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0F1115",
        panel: "#171A21",
        panel2: "#1D212A",
        panel3: "#232833",
        border: "#262B36",
        fg: "#E6E9EF",
        muted: "#8A93A6",
        accent: "#4F7CFF",
        ok: "#2FBF71",
        warn: "#F2B33D",
        err: "#E5484D",
        run: "#6E56CF",
        tiktok: "#25F4EE",
        yt: "#FF0033",
        fb: "#0866FF",
        ig: "#E1306C",
      },
      borderRadius: { card: "12px" },
    },
  },
  plugins: [],
};

export default config;
