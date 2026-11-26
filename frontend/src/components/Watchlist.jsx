import { useEffect, useState } from "react";
import { api, money } from "../api.js";
import PriceChart from "./PriceChart.jsx";

function WatchRow({ item, onUpdate, onRemove }) {
  const [editing, setEditing] = useState(false);
  const [target, setTarget] = useState(String(item.target_price));
  const [history, setHistory] = useState([]);

  useEffect(() => {
    api.history(item.id).then(setHistory).catch(() => setHistory([]));
  }, [item.id, item.latest_checked_at]);

  const save = async (e) => {
    e.preventDefault();
    try {
      await onUpdate(item.id, target);
      setEditing(false);
    } catch {
      /* shown by App */
    }
  };

  return (
    <li className={item.below_target ? "watch hit" : "watch"}>
      <div className="watch-head">
        {item.game.thumb_url ? <img src={item.game.thumb_url} alt="" /> : <div className="thumb" />}
        <div className="grow">
          <strong>{item.game.title}</strong>
          <div className="small">
            Now <b>{money(item.latest_price)}</b>
            {item.latest_store && <span className="muted"> at {item.latest_store}</span>}
            {item.latest_deal_url && (
              <>
                {" · "}
                <a href={item.latest_deal_url} target="_blank" rel="noreferrer">
                  view deal
                </a>
              </>
            )}
          </div>
        </div>
        {editing ? (
          <form className="row tight" onSubmit={save}>
            <input
              className="price"
              type="number"
              min="0.01"
              step="0.01"
              aria-label="New target price"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            />
            <button>Save</button>
            <button type="button" className="ghost" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <div className="row tight">
            <span className="target">
              Target {money(item.target_price)}
              {item.below_target && <span className="pill good">below!</span>}
            </span>
            <button className="ghost" onClick={() => setEditing(true)}>
              Edit
            </button>
            <button className="ghost danger" onClick={() => onRemove(item.id).catch(() => {})}>
              Remove
            </button>
          </div>
        )}
      </div>
      <PriceChart points={history} target={item.target_price} />
    </li>
  );
}

export default function Watchlist({ items, onUpdate, onRemove }) {
  return (
    <>
      <h2>Watchlist</h2>
      {items.length === 0 ? (
        <p className="muted">Nothing watched yet. Search a game and click Watch.</p>
      ) : (
        <ul className="watchlist">
          {items.map((item) => (
            <WatchRow key={item.id} item={item} onUpdate={onUpdate} onRemove={onRemove} />
          ))}
        </ul>
      )}
    </>
  );
}
