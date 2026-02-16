import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { fetchJSON, fetchCSV } from "../lib/csv";
import { TABS } from "../lib/constants";

const DataContext = createContext(null);

export function DataProvider({ children }) {
  const [manifest, setManifest] = useState(null);
  const [stateDataCache, setStateDataCache] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJSON("states.json")
      .then((data) => {
        setManifest(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const loadStateData = useCallback(
    async (stateCode) => {
      if (stateDataCache[stateCode]) return stateDataCache[stateCode];

      const state = manifest?.states?.find((s) => s.code === stateCode);
      if (!state) return null;

      const csvFiles = {};
      const promises = TABS.map(async (tab) => {
        try {
          const data = await fetchCSV(`${stateCode}/${tab.key}.csv`);
          csvFiles[tab.key] = data;
        } catch {
          csvFiles[tab.key] = [];
        }
      });

      // Also load annotations if they exist
      promises.push(
        fetchJSON(`${stateCode}/annotations.json`)
          .then((data) => { csvFiles.annotations = data; })
          .catch(() => { csvFiles.annotations = []; })
      );

      await Promise.all(promises);

      const result = { ...csvFiles, meta: state };
      setStateDataCache((prev) => ({ ...prev, [stateCode]: result }));
      return result;
    },
    [manifest, stateDataCache]
  );

  return (
    <DataContext.Provider value={{ manifest, loading, error, loadStateData, stateDataCache }}>
      {children}
    </DataContext.Provider>
  );
}

export function useData() {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used within DataProvider");
  return ctx;
}
