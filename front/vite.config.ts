import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

// Абсолютный путь: scss-резолвер не знает про алиас "@".
const stylesEntry = fileURLToPath(new URL("./src/assets/styles", import.meta.url));

// https://vite.dev/config/
export default defineConfig({
    plugins: [ react() ],
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    /**
     * В dev запросы идут на nginx: сервис api порт на хост не публикует,
     * а nginx сам срезает префикс /api. В продакшене тем же занимается
     * nginx внутри контейнера.
     */
    server: {
        proxy: {
            "/api": {
                target: "http://localhost:80",
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, ""),
            },
        },
    },
    css: {
        preprocessorOptions: {
            scss: {
                additionalData: `@use "${ stylesEntry }" as *;\n`,
            },
        },
    },
});
