import { useState } from "react";

import MatchFormWidget from "@/widgets/MatchFormWidget/MatchFormWidget";
import SidebarWidget from "@/widgets/SidebarWidget/SidebarWidget";
import type { SidebarScreen } from "@/widgets/SidebarWidget/SidebarWidget";

import styles from "./MainPage.module.scss";

export default function MainPage() {
    const [ screen, setScreen ] = useState<SidebarScreen>( "match" );

    return (
        <div className={styles.page}>
            <SidebarWidget
                activeScreen={ screen }
                onNavigate={ setScreen }
                shortListCount={ 8 }
            />

            <main className={styles.content}>
                { screen === "match" ? <MatchFormWidget /> : screen }
            </main>
        </div>
    );
}
