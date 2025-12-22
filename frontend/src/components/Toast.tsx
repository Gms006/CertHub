type ToastProps = {
  message: string;
  tone?: "success" | "error";
};

const Toast = ({ message, tone = "success" }: ToastProps) => {
  const styles =
    tone === "error"
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : "border-emerald-200 bg-emerald-50 text-emerald-700";

  return (
    <div
      className={`fixed bottom-5 right-5 z-50 rounded-2xl border px-4 py-3 text-sm shadow-soft ${styles}`}
    >
      {message}
    </div>
  );
};

export default Toast;
