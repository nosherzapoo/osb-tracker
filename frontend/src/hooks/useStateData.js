import { useState, useEffect } from "react";
import { useData } from "../context/DataContext";

export function useStateData(stateCode) {
  const { loadStateData, stateDataCache } = useData();
  const [data, setData] = useState(stateDataCache[stateCode] || null);
  const [loading, setLoading] = useState(!stateDataCache[stateCode]);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!stateCode) return;
    if (stateDataCache[stateCode]) {
      setData(stateDataCache[stateCode]);
      setLoading(false);
      return;
    }

    setLoading(true);
    loadStateData(stateCode)
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [stateCode, loadStateData, stateDataCache]);

  return { data, loading, error };
}
