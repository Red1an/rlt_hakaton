import type { SidebarScreen } from "@/widgets/SidebarWidget/SidebarWidget";

export const ROUTES = {
    MAIN: "/",
    SECTION: "/:section",
};

export const SCREEN_PATHS: Record<SidebarScreen, string> = {
    match: "/match",
    batch: "/batch",
    enrichment: "/enrichment",
    short: "/shortlist",
};

export function screenFromPath(pathname: string): SidebarScreen | null {
    const entry = Object.entries(SCREEN_PATHS).find(([ , path ]) => path === pathname);

    return entry ? entry[0] as SidebarScreen : null;
}
