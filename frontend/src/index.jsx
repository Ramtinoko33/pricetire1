import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import api from "@/lib/api";

async function boot() {
  // __USE_MOCK__ é substituído em tempo de build (vite.config.mjs). Sem VITE_USE_MOCK=1
  // a condição é `false` e o módulo de mock não entra no bundle.
  if (__USE_MOCK__) {
    const { installMock } = await import("./lib/mock");
    installMock(api);
  }
  const root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

boot();
