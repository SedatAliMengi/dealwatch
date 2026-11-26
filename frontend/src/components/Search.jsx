import { useEffect, useState } from "react";
import { api, money } from "../api.js";

// ?q=batman in the page URL pre-fills and runs a search (handy for sharing).
const initialQuery = new URLSearchParams(window.location.search).get("q") || "";

export default function Search({ watchedIds, onAdd }) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [targets, setTargets] = useState({});

  useEffect(() => {
    if (initialQuery) search();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const search = async (e) => {
    e?.preventDefault();
    if (query.trim().length < 2) {
      setMessage("Type at least 2 letters.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const found = await api.search(query.trim());
      setResults(found);
      if (found.length === 0) setMessage("No games found.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  };

  const add = async (game) => {
    const fallback = game.cheapest_price ? (game.cheapest_price * 0.8).toFixed(2) : "10.00";
    const target = targets[game.external_id] ?? fallback;
    try {
      await onAdd(game.external_id, target);
    } catch {
      /* error already shown by App */
    }
  };

  return (
    <>
      <h2>Search games</h2>
      <form className="row" onSubmit={search}>
        <input
          aria-label="Game title"
          placeholder="e.g. Hollow, Batman, Portal…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button disabled={loading}>{loading ? "Searching…" : "Search"}</button>
      </form>
      {message && <p className="muted">{message}</p>}
      {results.length > 0 && (
        <ul className="results">
          {results.map((g) => {
            const watched = watchedIds.has(g.external_id);
            return (
              <li key={g.external_id}>
                {g.thumb_url ? <img src={g.thumb_url} alt="" /> : <div className="thumb" />}
                <div className="grow">
                  <strong>{g.title}</strong>
                  <div className="muted small">Cheapest now: {money(g.cheapest_price)}</div>
                </div>
                {watched ? (
                  <span className="pill">Watching</span>
                ) : (
                  <div className="row tight">
                    <span className="muted small">Alert under $</span>
                    <input
                      className="price"
                      type="number"
                      min="0.01"
                      step="0.01"
                      aria-label={`Target price for ${g.title}`}
                      placeholder={g.cheapest_price ? (g.cheapest_price * 0.8).toFixed(2) : "10.00"}
                      value={targets[g.external_id] ?? ""}
                      onChange={(e) => setTargets({ ...targets, [g.external_id]: e.target.value })}
                    />
                    <button onClick={() => add(g)}>Watch</button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
