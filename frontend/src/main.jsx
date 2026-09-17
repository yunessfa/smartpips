import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { I18nProvider } from "./i18n/index.jsx";
import { AuthProvider } from "./auth/AuthContext.jsx";
import { LivePriceProvider } from "./live/LivePrices.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <I18nProvider>
      <AuthProvider>
        <LivePriceProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </LivePriceProvider>
      </AuthProvider>
    </I18nProvider>
  </React.StrictMode>
);

// Register the service worker for PWA install + push notifications.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
