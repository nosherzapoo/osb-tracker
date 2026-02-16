import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { PAGES } from "../lib/constants";

export function useKeyboardShortcuts() {
  const navigate = useNavigate();

  useEffect(() => {
    function handler(e) {
      // Ignore when typing in inputs
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;

      // Number keys 1-5 for page navigation
      const page = PAGES.find((p) => p.shortcut === e.key);
      if (page) {
        e.preventDefault();
        navigate(page.path);
        return;
      }

      // 'e' for export (dispatches custom event)
      if (e.key === "e") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("osb:export"));
        return;
      }

      // '?' for help
      if (e.key === "?") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("osb:help"));
        return;
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate]);
}
