import { useState } from "react";

import MatchFormWidget from "@/widgets/MatchFormWidget/MatchFormWidget";
import SidebarWidget from "@/widgets/SidebarWidget/SidebarWidget";
import type { SidebarScreen } from "@/widgets/SidebarWidget/SidebarWidget";
import VariantsWidget from "@/widgets/VariantsWidget/VariantsWidget";

import styles from "./MainPage.module.scss";

export default function MainPage() {
    const [ screen, setScreen ] = useState<SidebarScreen>( "match" );
    const [ hasSearched, setHasSearched ] = useState(false);

    function handleNavigate(next: SidebarScreen) {
        setScreen(next);

        // Уходя с «Подбора», прячем прошлую выдачу — при возврате снова форма.
        if (next !== "match") {
            setHasSearched(false);
        }
    }

    return (
        <div className={styles.page}>
            <SidebarWidget
                activeScreen={ screen }
                onNavigate={ handleNavigate }
                shortListCount={ 8 }
            />

            <main className={styles.content}>
                { screen === "match" ? (
                    <>
                        <MatchFormWidget onSearched={() => setHasSearched(true)} />

                        { hasSearched && <VariantsWidget /> }
                    </>
                ) : screen }
            </main>
        </div>
    );
}
