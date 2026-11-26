import { money } from "../api.js";

export default function Alerts({ alerts, onRead, onReadAll }) {
  const unread = alerts.filter((a) => !a.is_read).length;
  const ignore = () => {};

  return (
    <>
      <div className="row space">
        <h2>
          Alerts {unread > 0 && <span className="badge">{unread}</span>}
        </h2>
        {unread > 0 && (
          <button className="ghost" onClick={() => onReadAll().catch(ignore)}>
            Mark all read
          </button>
        )}
      </div>
      {alerts.length === 0 ? (
        <p className="muted">No alerts yet. You'll see one when a price drops below your target.</p>
      ) : (
        <ul className="alerts">
          {alerts.map((a) => (
            <li key={a.id} className={a.is_read ? "read" : "unread"}>
              <div>
                <strong>{a.game_title}</strong> is <b>{money(a.price)}</b> at {a.store_name}
                <div className="muted small">
                  Your target: {money(a.target_price)} ·{" "}
                  {new Date(a.created_at).toLocaleString()}
                </div>
              </div>
              <div className="row tight">
                {a.deal_url && (
                  <a href={a.deal_url} target="_blank" rel="noreferrer">
                    Deal
                  </a>
                )}
                {!a.is_read && (
                  <button className="ghost" onClick={() => onRead(a.id).catch(ignore)}>
                    Mark read
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
