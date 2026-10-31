import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createHashRouter, RouterProvider } from "react-router-dom";
import "./styles.css";
import App from "./App";
import { overviewLoader } from "./loaders";

const router = createHashRouter([
  {
    path: "/",
    element: <App />,
    loader: overviewLoader,
    children: [
      { index: true, lazy: () => import("./pages/Overview") },
      { path: "metrics", lazy: () => import("./pages/Metrics") },
      { path: "tools", lazy: () => import("./pages/Tools") },
      { path: "boundaries", lazy: () => import("./pages/Boundaries") },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
