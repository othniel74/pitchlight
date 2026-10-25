import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ArrowRight, Network } from "lucide-react";
import { withMatch } from "./match";
import "./structure.css";

// How a team plays, in five plain views: where it attacks, how roles changed, who its passing relies
// on, who wins the ball from whom, and the moves it repeats. Each view leads with one sentence,
// shows one picture, and keeps the evidence one click away.

type Ev = { id: string; clock: number; player: string; type: string; to: string | null };
type Channel = { passes: number; share: number; recent_share: number; before_share: number; event_ids: string[] };
type Structure = {
  events: Record<string, Ev>;
  zones: { headline: string; window: number; final_third_passes: number; recent_passes: number;
           channels: Record<"left" | "centre" | "right", Channel>;
           points: { x: number; ay: number; channel: string; recent: boolean; id: string }[] };
  roles: { headline: string; step: number;
           spells: { start: number; end: number; hub: string | null; key_link: string | null }[];
           changes: { minute: number; text: string; event_ids: string[] }[];
           players: { player: string; name: string; hub: number[][]; key_link: number[][] }[] };
  dependency: { headline: string; passes: number;
                players: { player: string; name: string; share: number; pass_share: number }[];
                nodes: { player: string; name: string; shirt: number | null; x: number; ay: number; unit: number | null }[];
                edges: { from: string; to: string; passes: number; event_ids: string[] }[];
                units: { player: string; name: string }[][] };
  duels: { headline: string; won: number; won_in_opponent_half: number;
           pairs: { winner_name: string; loser_name: string; count: number; event_ids: string[]; points: { x: number; ay: number }[] }[];
           points: { x: number; ay: number; id: string }[] };
  patterns: { headline: string; min_count: number;
              moves: { names: string[]; one_two: boolean; count: number; shots: number; goals: number; event_ids: string[] }[] };
};

const TABS = [
  { id: "zones", label: "Where they attack" },
  { id: "roles", label: "Roles over time" },
  { id: "dependency", label: "Who they rely on" },
  { id: "duels", label: "Winning the ball" },
  { id: "patterns", label: "Repeated moves" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const UNIT_COLOURS = ["#c5f277", "#779ef9", "#f2b277", "#d38bf2"];
const clock = (s: number) => `${Math.floor(s / 60) + 1}′`;
// Pitch drawn in the attacking team's view: attacking to the right, their left at the top.
const px = (x: number) => (x * 1.05).toFixed(1);
const py = (ay: number) => ((100 - ay) * 0.68).toFixed(1);

function Pitch({ children, label }: { children: ReactNode; label: string }) {
  return (
    <svg className="structure-pitch" viewBox="-2 -2 109 72" role="img" aria-label={label}>
      <rect x="0" y="0" width="105" height="68" className="pitch-turf" />
      <g className="pitch-lines">
        <rect x="0" y="0" width="105" height="68" />
        <line x1="52.5" y1="0" x2="52.5" y2="68" />
        <circle cx="52.5" cy="34" r="9.15" />
        <rect x="0" y="13.84" width="16.5" height="40.32" />
        <rect x="88.5" y="13.84" width="16.5" height="40.32" />
      </g>
      {children}
    </svg>
  );
}

function Evidence({ ids, events, label = "Show the events behind this" }: { ids: string[]; events: Record<string, Ev>; label?: string }) {
  const rows = ids.map((i) => events[i]).filter(Boolean).sort((a, b) => a.clock - b.clock);
  if (!rows.length) return null;
  return (
    <details className="structure-evidence">
      <summary>{label} ({rows.length})</summary>
      <ol>
        {rows.slice(-24).map((e) => (
          <li key={e.id}><span>{clock(e.clock)}</span> {e.player} · {e.type}{e.to ? ` → ${e.to}` : ""}</li>
        ))}
      </ol>
    </details>
  );
}

function Zones({ data, events }: { data: Structure["zones"]; events: Record<string, Ev> }) {
  const lanes = [["left", 66.67, 100], ["centre", 33.33, 66.67], ["right", 0, 33.33]] as const;
  return (
    <div className="structure-split">
      <Pitch label="Final-third passes by channel, attacking to the right">
        {lanes.map(([name, lo, hi]) => (
          <g key={name}>
            <rect x={px(66.67)} y={py(hi)} width={(33.33 * 1.05).toFixed(1)} height={((hi - lo) * 0.68).toFixed(1)}
                  className="zone-band" style={{ opacity: 0.12 + data.channels[name].share / 130 }} />
            <text x={px(98)} y={(Number(py(hi)) + (hi - lo) * 0.34 + 2).toFixed(1)} className="zone-label" textAnchor="end">
              {data.channels[name].share}%
            </text>
          </g>
        ))}
        {data.points.map((p) => (
          <circle key={p.id} cx={px(p.x)} cy={py(p.ay)} r="0.9" className={p.recent ? "dot-recent" : "dot-before"} />
        ))}
        <text x="3" y="66" className="pitch-note">Attacking →</text>
      </Pitch>
      <div className="structure-side">
        <table className="graph-table" aria-label="Final-third passes by channel">
          <thead><tr><th>Channel</th><th>So far</th><th>Before</th><th>Last {data.window}′</th></tr></thead>
          <tbody>
            {(["left", "centre", "right"] as const).map((c) => (
              <tr key={c}><td>{c[0].toUpperCase() + c.slice(1)}</td><td>{data.channels[c].share}%</td>
                <td>{data.channels[c].before_share}%</td><td>{data.channels[c].recent_share}%</td></tr>
            ))}
          </tbody>
        </table>
        <p className="subtle-note">
          {data.final_third_passes} completed passes into or within the final third. <i className="key-recent" /> last {data.window} minutes,
          <i className="key-before" /> earlier.
        </p>
        <Evidence ids={Object.values(data.channels).flatMap((c) => c.event_ids)} events={events} />
      </div>
    </div>
  );
}

function Roles({ data, minute, events }: { data: Structure["roles"]; minute: number; events: Record<string, Ev> }) {
  const span = Math.max(minute, 1);
  const seg = (a: number, b: number) => ({ left: `${(a / span) * 100}%`, width: `${((b - a) / span) * 100}%` });
  return (
    <div>
      {data.players.length ? (
        <div className="role-strips" role="table" aria-label="Who held each role, by minute">
          {data.players.map((p) => (
            <div className="role-strip" role="row" key={p.player}>
              <span role="rowheader">{p.name}</span>
              <div className="role-track" role="cell">
                {p.hub.map(([a, b]) => <i key={`h${a}`} className="role-hub" style={seg(a, b)} title={`Hub ${a}–${b}′`} />)}
                {p.key_link.map(([a, b]) => <i key={`k${a}`} className="role-key" style={seg(a, b)} title={`Key link ${a}–${b}′`} />)}
              </div>
            </div>
          ))}
          <div className="role-axis" aria-hidden="true"><span>0′</span><span>{Math.round(span / 2)}′</span><span>{span}′</span></div>
        </div>
      ) : <p className="subtle-note">Roles appear once a team has completed enough passes.</p>}
      <p className="role-legend"><i className="role-hub" /> Hub: most passes made and received
        <i className="role-key" /> Key link: connects the most teammates</p>
      {data.changes.length > 0 && (
        <ul className="structure-cards">
          {[...data.changes].reverse().map((c) => (
            <li key={`${c.minute}${c.text}`}>
              <p>{c.text}</p>
              <Evidence ids={c.event_ids} events={events} label="Passes involving them" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Dependency({ data, events }: { data: Structure["dependency"]; events: Record<string, Ev> }) {
  const [removed, setRemoved] = useState<string | null>(null);
  const pick = removed ?? data.players[0]?.player ?? null;
  const at = useMemo(() => Object.fromEntries(data.nodes.map((n) => [n.player, n])), [data.nodes]);
  const chosen = data.players.find((p) => p.player === pick);
  const max = Math.max(1, ...data.edges.map((e) => e.passes));
  const busiest = Math.max(1, ...data.players.map((p) => p.pass_share));
  return (
    <div className="structure-split">
      <Pitch label="Passing network with the chosen player removed">
        {data.edges.map((e) => at[e.from] && at[e.to] && (
          <line key={`${e.from}-${e.to}`} x1={px(at[e.from].x)} y1={py(at[e.from].ay)} x2={px(at[e.to].x)} y2={py(at[e.to].ay)}
                className={e.from === pick || e.to === pick ? "lane-cut" : "lane"} style={{ strokeWidth: 0.25 + (e.passes / max) * 1.4 }} />
        ))}
        {data.nodes.map((n) => (
          <g key={n.player} className={n.player === pick ? "node-out" : "node"}>
            <circle cx={px(n.x)} cy={py(n.ay)} r="2.6" style={{ fill: n.unit != null ? UNIT_COLOURS[n.unit % 4] : "#949ba9" }} />
            <text x={px(n.x)} y={(Number(py(n.ay)) + 1).toFixed(1)} textAnchor="middle">{n.shirt ?? ""}</text>
          </g>
        ))}
      </Pitch>
      <div className="structure-side">
        {chosen && (
          <p className="structure-what-if">
            <b>{chosen.pass_share}%</b> of the team's passes involved <b>{chosen.name}</b>. Take them out and the passing network
            is <b>{chosen.share ? `${chosen.share}%` : "less than 1%"}</b> less connected.
          </p>
        )}
        <div className="dependency-list" role="group" aria-label="Choose a player to take out">
          {data.players.slice(0, 8).map((p) => (
            <button key={p.player} type="button" aria-pressed={p.player === pick} onClick={() => setRemoved(p.player)}>
              <span>{p.name}</span><i style={{ width: `${Math.max((p.pass_share / busiest) * 100, 4)}%` }} title={`${p.pass_share}% of passes`} /><b>{p.share ? `−${p.share}%` : "<1%"}</b>
            </button>
          ))}
        </div>
        {data.units.length > 0 && (
          <div className="structure-units">
            <span>Passing units</span>
            {data.units.map((u, i) => (
              <p key={i}><i style={{ background: UNIT_COLOURS[i % 4] }} />{u.map((p) => p.name).join(", ")}</p>
            ))}
          </div>
        )}
        <p className="subtle-note">Bar: share of the team's passes. Number: how much less connected the network is without them. Lanes drawn are used twice or more; players who pass most among themselves form a unit.</p>
        <Evidence ids={data.edges.filter((e) => e.from === pick || e.to === pick).flatMap((e) => e.event_ids)} events={events}
                  label="Passes through this player" />
      </div>
    </div>
  );
}

function Duels({ data, events }: { data: Structure["duels"]; events: Record<string, Ev> }) {
  const [chosen, setChosen] = useState(0);
  const pair = data.pairs[chosen];
  return (
    <div className="structure-split">
      <Pitch label="Where the ball was won, attacking to the right">
        {data.points.map((p) => <circle key={p.id} cx={px(p.x)} cy={py(p.ay)} r="1" className="dot-before" />)}
        {pair?.points.map((p, i) => <circle key={i} cx={px(p.x)} cy={py(p.ay)} r="1.8" className="dot-recent" />)}
        <text x="3" y="66" className="pitch-note">Attacking →</text>
      </Pitch>
      <div className="structure-side">
        <p className="subtle-note">Won the ball back {data.won} times, {data.won_in_opponent_half} of them in the opponent's half.</p>
        <div className="duel-list" role="group" aria-label="Who won the ball from whom">
          {data.pairs.map((p, i) => (
            <button key={`${p.winner_name}${p.loser_name}`} type="button" aria-pressed={i === chosen} onClick={() => setChosen(i)}>
              <span><b>{p.winner_name}</b> won it from {p.loser_name}</span><b>{p.count}</b>
            </button>
          ))}
        </div>
        {pair && <Evidence ids={pair.event_ids} events={events} />}
      </div>
    </div>
  );
}

function Patterns({ data, events }: { data: Structure["patterns"]; events: Record<string, Ev> }) {
  if (!data.moves.length) return <p className="subtle-note">No three-player move repeated {data.min_count} times yet.</p>;
  return (
    <ul className="structure-cards moves">
      {data.moves.map((m) => (
        <li key={m.names.join(">")}>
          <p className="move-chain">
            {m.names.map((n, i) => <span key={i}>{i > 0 && <ArrowRight size={12} aria-hidden="true" />}{n}</span>)}
          </p>
          <p className="move-stats">
            {m.one_two ? "One-two · " : ""}{m.count} times · {m.shots} ended in a shot{m.goals ? ` · ${m.goals} in a goal` : ""}
          </p>
          <Evidence ids={m.event_ids} events={events} label="The passes" />
        </li>
      ))}
    </ul>
  );
}

export function StructurePanel({ minute, clubs }: { minute: number; clubs: Record<string, { short: string }> }) {
  const [team, setTeam] = useState<"home" | "away">("away");
  const [tab, setTab] = useState<Tab>("zones");
  const [data, setData] = useState<Structure | null>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const bucket = Math.max(5, Math.floor(minute / 5) * 5);  // refresh every five minutes of match time
  useEffect(() => {
    let cancelled = false;
    fetch(withMatch(`/api/graph/structure?team=${team}&minute=${bucket}`)).then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled && d) setData(d); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [team, bucket]);
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (i + step + TABS.length) % TABS.length;
    setTab(TABS[next].id);
    tabs.current[next]?.focus();
  };
  const view = data?.[tab];
  return (
    <section className="panel structure-panel" aria-label="How the team plays">
      <div className="panel-title">
        <h2><Network size={17} />How {clubs[team]?.short ?? "the team"} play</h2>
        <div className="structure-teams" role="group" aria-label="Team">
          {(["home", "away"] as const).map((t) => (
            <button key={t} type="button" className={`player-chip ${team === t ? "on" : ""}`} aria-pressed={team === t}
                    onClick={() => setTeam(t)}>{clubs[t]?.short ?? t}</button>
          ))}
        </div>
      </div>
      <div className="structure-tabs" role="tablist" aria-label="View">
        {TABS.map((t, i) => (
          <button key={t.id} ref={(el) => { tabs.current[i] = el; }} role="tab" id={`structure-tab-${t.id}`}
                  aria-selected={tab === t.id} aria-controls="structure-view" tabIndex={tab === t.id ? 0 : -1}
                  onClick={() => setTab(t.id)} onKeyDown={(e) => onKey(e, i)}>{t.label}</button>
        ))}
      </div>
      <div className="structure-view" role="tabpanel" id="structure-view" aria-labelledby={`structure-tab-${tab}`}>
        {!data || !view ? <p className="subtle-note">Reading the match…</p> : (
          <>
            <p className="structure-headline" data-testid="structure-headline">{view.headline}</p>
            {tab === "zones" && <Zones data={data.zones} events={data.events} />}
            {tab === "roles" && <Roles data={data.roles} minute={bucket} events={data.events} />}
            {tab === "dependency" && <Dependency key={team} data={data.dependency} events={data.events} />}
            {tab === "duels" && <Duels key={team} data={data.duels} events={data.events} />}
            {tab === "patterns" && <Patterns data={data.patterns} events={data.events} />}
          </>
        )}
      </div>
      <p className="structure-foot">Up to minute {bucket}. Describes what happened in the events; it never claims why.</p>
    </section>
  );
}
