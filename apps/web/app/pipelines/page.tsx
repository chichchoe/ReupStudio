export default function Page() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold">Luồng tự động</h1>
      <p className="text-[13px] text-muted mt-1">Thuộc chặng <b>M7</b> — chưa triển khai.</p>
      <div className="card mt-5 text-[12.5px] text-muted">
        <p>Nối kênh nguồn Trung Quốc thẳng tới kênh Việt Nam: quét định kỳ, xử lý, xếp lịch và đăng mà không cần thao tác tay.</p>
        <p className="mt-2">
          Xem chi tiết task trong <code className="font-mono">docs/03-BACKLOG-CONG-VIEC.md</code>.
        </p>
      </div>
    </div>
  );
}
