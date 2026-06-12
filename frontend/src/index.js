import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { PipelineProvider } from "./context/PipelineContext";
import "./styles/main.css";
import "./index.css";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <PipelineProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </PipelineProvider>
  </React.StrictMode>
);
