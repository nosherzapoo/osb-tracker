/**
 * CSV loading via PapaParse.
 */

import Papa from "papaparse";
import { DATA_BASE_URL } from "./constants";

export async function fetchCSV(path) {
  const url = `${DATA_BASE_URL}/${path}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Failed to fetch ${url}: ${resp.status}`);
  const text = await resp.text();
  const { data } = Papa.parse(text, { header: true, skipEmptyLines: true });
  return data;
}

export async function fetchJSON(path) {
  const url = `${DATA_BASE_URL}/${path}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Failed to fetch ${url}: ${resp.status}`);
  return resp.json();
}
