import { useState, useEffect, useCallback } from "react";
import styles from "./Toast.module.css";

let showToastFn = null;

export function showToast(message, type = "info") {
  if (showToastFn) showToastFn(message, type);
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  useEffect(() => {
    showToastFn = addToast;
    return () => { showToastFn = null; };
  }, [addToast]);

  return (
    <div className={styles.container}>
      {toasts.map((t) => (
        <div key={t.id} className={`${styles.toast} ${styles[t.type]}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}
