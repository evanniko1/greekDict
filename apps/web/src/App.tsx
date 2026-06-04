import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import SearchPage from "./pages/SearchPage";
import WordPage from "./pages/WordPage";
import ExplorePage from "./pages/ExplorePage";
import MethodologyPage from "./pages/MethodologyPage";
import LicensingPage from "./pages/LicensingPage";
import AboutPage from "./pages/AboutPage";
import Footer from "./components/Footer";
import ThemeToggle from "./components/ThemeToggle";
import { useTheme } from "./hooks/useTheme";

export default function App() {
  const { theme, toggle } = useTheme();
  return (
    <BrowserRouter>
      <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <header className="border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-4">
            <Link to="/" className="text-2xl font-bold tracking-tight">
              Λεξόραμα
            </Link>
            <div className="flex items-center gap-4">
              <Link
                to="/explore"
                className="text-sm font-medium text-slate-500 transition hover:text-violet-600 dark:text-slate-400 dark:hover:text-violet-300"
              >
                Εξερεύνηση
              </Link>
              <Link
                to="/methodology"
                className="text-sm font-medium text-slate-500 transition hover:text-violet-600 dark:text-slate-400 dark:hover:text-violet-300"
              >
                Μεθοδολογία
              </Link>
              <ThemeToggle theme={theme} onToggle={toggle} />
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl px-4 py-6">
          <Routes>
            <Route path="/" element={<SearchPage />} />
            <Route path="/word/:lemma" element={<WordPage />} />
            <Route path="/explore" element={<ExplorePage />} />
            <Route path="/methodology" element={<MethodologyPage />} />
            <Route path="/movers" element={<Navigate to="/explore" replace />} />
            <Route path="/licensing" element={<LicensingPage />} />
            <Route path="/about" element={<AboutPage />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  );
}
