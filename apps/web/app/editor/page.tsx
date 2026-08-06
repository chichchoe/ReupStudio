export default function Page() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold">Editor</h1>
      <p className="text-[13px] text-muted mt-1">Thuộc chặng <b>M3–M4</b> — chưa triển khai.</p>
      <div className="card mt-5 text-[12.5px] text-muted">
        <p>Vẽ mask xoá watermark và phụ đề cứng, sửa phụ đề tiếng Việt, chuẩn hoá khung hình 9:16 và hook 3 giây đầu.</p>
        <p className="mt-2">
          Xem chi tiết task trong <code className="font-mono">docs/03-BACKLOG-CONG-VIEC.md</code>.
        </p>
      </div>
    </div>
  );
}
