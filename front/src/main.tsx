import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./configs/RoutesConfig.tsx";
import "./index.scss";

const root = ReactDOM.createRoot(document.getElementById("root")!);
root.render(
    <React.StrictMode>
        <RouterProvider router={ router } />
    </React.StrictMode>,
);
