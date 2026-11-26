import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Search from "./components/Search.jsx";
import Watchlist from "./components/Watchlist.jsx";
import Alerts from "./components/Alerts.jsx";

export default function App() {
  const [items, setItems] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const [lastCheck, setLastCheck] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [w, a] = await Promise.all([api.watchlist(), api.alerts()]);
      setItems(w);
      setAlerts(a);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Wrap an action: run it, show any error, then reload the data.
  const act = (fn) => async (...args) => {
    try {
      await fn(...args);
      setError("");
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      refresh();
    }
  };

  const runCheck = async () => {
    setChecking(true);
    try {
      setLastCheck(await api.runCheck());
    } catch (e) {
      setError(e.message);
    } finally {
      setChecking(false);
      refresh();
    }
  };

  const watchedIds = new Set(items.map((i) => i.game.external_id));

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Dealwatch</h1>
          <p className="muted">Game price alerts across Steam, Epic, GOG and more.</p>
        </div>
        <div className="check">
          <button onClick={runCheck} disabled={checking}>
            {checking ? "Checking…" : "Check prices now"}
          </button>
          {lastCheck && (
            <span className="muted small">
              Checked {lastCheck.checked} · {lastCheck.alerts_created} new alert(s)
            </span>
          )}
        </div>
      </header>

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}

      <main className="grid">
        <section className="card span-2">
          <Search watchedIds={watchedIds} onAdd={act(api.addWatch)} />
        </section>
        <section className="card span-2">
          <Watchlist
            items={items}
            onUpdate={act(api.updateWatch)}
            onRemove={act(api.removeWatch)}
          />
        </section>
        <section className="card">
          <Alerts
            alerts={alerts}
            onRead={act(api.markRead)}
            onReadAll={act(api.markAllRead)}
          />
        </section>
      </main>

      <footer className="muted small">
        Price data from{" "}
        <a href="https://www.cheapshark.com" target="_blank" rel="noreferrer">
          CheapShark
        </a>
        . Deal links go through CheapShark.
      </footer>
    </div>
  );
}
