import {
    Navigate, createBrowserRouter,
} from "react-router-dom";
import {
    ROUTES, SCREEN_PATHS,
} from "./RoutesConst";

import EmptyLayout from "@/layouts/EmptyLayout";
import MainPage from "@/pages/MainPage.tsx";

export const routesConfig = [
    {
        element: <EmptyLayout />,
        children: [
            {
                path: ROUTES.SECTION,
                element: <MainPage />,
            },
            {
                path: "*",
                element: <Navigate to={ SCREEN_PATHS.match } replace />,
            },
        ],
    },
];

export const router = createBrowserRouter(routesConfig);
