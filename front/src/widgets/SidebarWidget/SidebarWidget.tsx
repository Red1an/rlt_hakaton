import { useState } from "react";

import styles from "./SidebarWidget.module.scss";

export type SidebarScreen = "match" | "batch" | "enrichment" | "short";

interface SidebarItem {
    screen: SidebarScreen;
    label: string;
    iconId: string;
}

interface SidebarWidgetProps {
    activeScreen: SidebarScreen;
    onNavigate: (screen: SidebarScreen) => void;
    shortListCount: number;
    className?: string;
}

const SPRITE_URL = "/icons/sprite.svg";

const NAV_ITEMS: SidebarItem[] = [
    {
        screen: "match",
        label: "Подбор",
        iconId: "nav-match",
    },
    {
        screen: "batch",
        label: "Пакетный подбор",
        iconId: "nav-market",
    },
    {
        screen: "enrichment",
        label: "Обогащение",
        iconId: "nav-quality",
    },
    {
        screen: "short",
        label: "Шорт-лист",
        iconId: "nav-short",
    },
];

export default function SidebarWidget({
    activeScreen,
    onNavigate,
    shortListCount,
    className,
}: SidebarWidgetProps) {
    const [ collapsed, setCollapsed ] = useState(false);

    const rootClassName = [
        styles.sidebar,
        collapsed ? styles.collapsed : "",
        className ?? "",
    ].filter(Boolean).join(" ");

    const renderItem = (item: SidebarItem) => {
        const isActive = item.screen === activeScreen;

        return (
            <button
                key={ item.screen }
                type="button"
                title={ item.label }
                aria-current={ isActive ? "page" : undefined }
                className={[ styles.item, isActive ? styles.itemActive : "" ].filter(Boolean).join(" ")}
                onClick={() => onNavigate(item.screen)}
            >
                <span className={styles.icon}>
                    <svg
                        width="18"
                        height="18"
                        viewBox="0 0 18 18"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={ 1.6 }
                        aria-hidden="true"
                    >
                        <use href={`${ SPRITE_URL }#${ item.iconId }`} />
                    </svg>
                </span>
                {!collapsed && <span className={styles.label}>{ item.label }</span>}
                {item.screen === "short" && (
                    <span className={styles.badge}>{ shortListCount }</span>
                )}
            </button>
        );
    };

    return (
        <nav className={rootClassName} aria-label="Основная навигация">
            { NAV_ITEMS.map(renderItem) }

            <div className={styles.spacer} />

            <button
                type="button"
                className={styles.collapseButton}
                onClick={() => setCollapsed(!collapsed)}
            >
                <span className={styles.collapseArrow}>{ collapsed ? "»" : "«" }</span>
                {!collapsed && <span>Свернуть меню</span>}
            </button>
        </nav>
    );
}
