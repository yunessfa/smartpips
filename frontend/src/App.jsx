import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Chat from "./pages/Chat.jsx";
import Sources from "./pages/Sources.jsx";
import AISettings from "./pages/AISettings.jsx";
import Trades from "./pages/Trades.jsx";

function Protected({ children }) {
  const { isAuthed, ready } = useAuth();
  const location = useLocation();
  if (!ready) {
    return (
      <div className="min-h-screen grid place-items-center bg-ink-900 text-mist-500">
        <span className="h-6 w-6 rounded-full border-2 border-mist-500 border-t-transparent animate-spin" />
      </div>
    );
  }
  if (!isAuthed) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <Protected>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/chat" element={<Chat />} />
                <Route path="/trades" element={<Trades />} />
                <Route path="/sources" element={<Sources />} />
                <Route path="/ai" element={<AISettings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          </Protected>
        }
      />
    </Routes>
  );
}
