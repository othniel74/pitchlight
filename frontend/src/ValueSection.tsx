import { useRef, useState, type KeyboardEvent } from "react";
import { ArrowRight, ArrowUpRight, Play } from "lucide-react";
import "./value.css";

// Who it helps: each visitor picks their role and sees the three pains they recognise,
// what Pitchlight does about each, and the measured result behind it.

type Row = { pain: string; gain: string; proof: string };
type Audience = { id: string; label: string; rows: Row[] };

const AUDIENCES: Audience[] = [
  {
    id: "broadcasters", label: "Broadcasters",
    rows: [
      { pain: "AI writes fast, but invents scorers and results. One wrong line on air costs trust.",
        gain: "Every statement is checked against the match before anyone sees it.",
        proof: "0 false statements in 264 live checks" },
      { pain: "Every AI-written line still needs a person to check it.",
        gain: "Editors review the evidence behind each claim instead of rewriting copy.",
        proof: "Every claim links to its source events" },
      { pain: "Each new language means a new team and a new cost.",
        gain: "One set of verified facts, published in seven languages.",
        proof: "Including Arabic, right to left" },
    ],
  },
  {
    id: "fan-apps", label: "Fan apps",
    rows: [
      { pain: "Every fan gets the same generic match report.",
        gain: "A personal story: your club, your player, the metric you care about.",
        proof: "Fan, analyst or broadcast mode" },
      { pain: "Fans' questions go unanswered, or a chatbot guesses.",
        gain: "Ask the match, and the answer comes from verified data.",
        proof: "A Foundry agent calling Pitchlight's own tools" },
      { pain: "Content arrives after the moment has passed.",
        gain: "Moments and recaps update while the match is being played.",
        proof: "Streamed live through Azure Event Hubs" },
    ],
  },
  {
    id: "clubs", label: "Clubs",
    rows: [
      { pain: "At half-time, analysts scrub through video to find what is going wrong.",
        gain: "Pressing, defensive shape and passing changes, in seconds.",
        proof: "Last 15 minutes compared with the 15 before" },
      { pain: "Did the substitution work, or was it just a lucky spell?",
        gain: "The ten minutes before and after every change, ranked against the match's normal swings.",
        proof: "Evidence for the next decision, never a claimed cause" },
      { pain: "Match reports for a global fanbase take hours.",
        gain: "Verified recaps in seven languages, minutes after the final whistle.",
        proof: "62 of 63 AI recaps published, none wrong" },
    ],
  },
  {
    id: "developers", label: "Developers",
    rows: [
      { pain: "Your own AI agents make up sports facts.",
        gain: "Fifteen verified, read-only match tools any agent can call.",
        proof: "MCP server and HTTP API" },
      { pain: "Every data provider uses a different format.",
        gain: "One validated data layer for events from any provider.",
        proof: "2,669 real matches checked, every score matched" },
      { pain: "It is hard to prove AI output is safe.",
        gain: "Measured results and an audit trail for every published claim.",
        proof: "Microsoft Foundry groundedness 4.71 / 5" },
    ],
  },
];

const PROOF = [
  { value: "62 / 63", label: "AI recaps published, none wrong" },
  { value: "0 / 264", label: "false statements let through" },
  { value: "4.71 / 5", label: "groundedness, Microsoft Foundry" },
  { value: "2,669", label: "real matches checked offline" },
];

export function ValueSection() {
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const audience = AUDIENCES[active];

  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (active + step + AUDIENCES.length) % AUDIENCES.length;
    setActive(next);
    tabs.current[next]?.focus();
  };

  return (
    <section className="lp-value lp-section" id="who-it-helps" aria-label="Who it helps">
      <div className="lp-section-top">
        <div>
          <span className="lp-eyebrow"><span /> WHO IT HELPS</span>
          <h2>
            AI can explain football.
            <br />
            <em>Pitchlight makes it safe to air.</em>
          </h2>
        </div>
        <p>
          Language models write well but invent facts, so nobody can put them on screen. Pick who you are to see
          what changes when every statement is checked first.
        </p>
      </div>

      <div className="lp-value-tabs" role="tablist" aria-label="Choose your role">
        {AUDIENCES.map((a, i) => (
          <button
            key={a.id}
            ref={(el) => { tabs.current[i] = el; }}
            role="tab"
            id={`value-tab-${a.id}`}
            aria-selected={i === active}
            aria-controls="value-panel"
            tabIndex={i === active ? 0 : -1}
            onClick={() => setActive(i)}
            onKeyDown={onKey}
          >
            {a.label}
          </button>
        ))}
      </div>

      <div className="lp-value-panel" role="tabpanel" id="value-panel" aria-labelledby={`value-tab-${audience.id}`}>
        <div className="lp-value-heads" aria-hidden="true">
          <span>Today</span>
          <span />
          <span>With Pitchlight</span>
        </div>
        {audience.rows.map((row) => (
          <div className="lp-value-row" key={row.pain}>
            <p className="lp-value-pain"><span className="lp-value-tag">Today</span>{row.pain}</p>
            <ArrowRight className="lp-value-arrow" size={20} aria-hidden="true" />
            <div className="lp-value-gain">
              <span className="lp-value-tag">With Pitchlight</span>
              <p>{row.gain}</p>
              <small>{row.proof}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="lp-value-proof">
        {PROOF.map((p) => (
          <div key={p.value}><strong>{p.value}</strong><span>{p.label}</span></div>
        ))}
      </div>

      <div className="lp-value-actions">
        <a href="/app?tour=1&speed=3" className="lp-button lp-button-lime">
          See it in 60 seconds <Play size={14} />
        </a>
        <a href="/app" className="lp-button lp-button-dark">
          Explore the workspace <ArrowUpRight size={15} />
        </a>
      </div>
    </section>
  );
}
