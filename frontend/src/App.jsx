import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { DataProvider } from "./context/DataContext";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import Layout from "./components/layout/Layout";
import ToastContainer from "./components/common/Toast";
import { ChartSkeleton } from "./components/common/Skeleton";

const NationalOverview = lazy(() => import("./pages/NationalOverview"));
const StateDeepDive = lazy(() => import("./pages/StateDeepDive"));
const OperatorTracker = lazy(() => import("./pages/OperatorTracker"));
const DataLab = lazy(() => import("./pages/DataLab"));
const About = lazy(() => import("./pages/About"));

function AppRoutes() {
  useKeyboardShortcuts();

  return (
    <Layout>
      <Suspense fallback={<ChartSkeleton height={400} />}>
        <Routes>
          <Route path="/" element={<NationalOverview />} />
          <Route path="/state" element={<StateDeepDive />} />
          <Route path="/state/:stateCode" element={<StateDeepDive />} />
          <Route path="/operator" element={<OperatorTracker />} />
          <Route path="/operator/:slug" element={<OperatorTracker />} />
          <Route path="/data-lab" element={<DataLab />} />
          <Route path="/about" element={<About />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <DataProvider>
        <AppRoutes />
        <ToastContainer />
      </DataProvider>
    </BrowserRouter>
  );
}
