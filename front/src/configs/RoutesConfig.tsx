import { createBrowserRouter } from "react-router-dom";
import { ROUTES } from "./RoutesConst";

import EmptyLayout from "@/layouts/EmptyLayout";
import MainPage from "@/pages/MainPage.tsx";

export const routesConfig = [
    {
        element: <EmptyLayout />,
        children: [
            {
                path: ROUTES.MAIN,
                element: <MainPage />,
            },
        ],
    },
];

export const router = createBrowserRouter(routesConfig);
