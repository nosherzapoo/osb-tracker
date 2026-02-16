import { useSearchParams } from "react-router-dom";
import { useCallback } from "react";

export function useURLState(key, defaultValue) {
  const [searchParams, setSearchParams] = useSearchParams();

  const value = searchParams.get(key) ?? defaultValue;

  const setValue = useCallback(
    (newValue) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (newValue === defaultValue || newValue == null) {
          next.delete(key);
        } else {
          next.set(key, newValue);
        }
        return next;
      }, { replace: true });
    },
    [key, defaultValue, setSearchParams]
  );

  return [value, setValue];
}
