import { Outlet } from "react-router-dom";


export default function EmptyLayout() {
    return (
        <div className="app-container">
            <div/>
            <main className="main-container">
                <Outlet />
            </main>
        </div>
    );
}
