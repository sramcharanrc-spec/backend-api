type ToastMessage = {
  id: string;
  tone: "success" | "info" | "warning";
  title: string;
  message: string;
};

type ToastStackProps = {
  toastMessages: ToastMessage[];
};

const ToastStack = ({ toastMessages }: ToastStackProps) => {
  if (!toastMessages.length) return null;

  return (
    <div className="cw-toast-stack">
      {toastMessages.map((toast) => (
        <div key={toast.id} className={`cw-toast ${toast.tone}`}>
          <strong>{toast.title}</strong>
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
};

export default ToastStack;