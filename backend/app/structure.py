"""Match structure: where a team attacks, how roles change, who the passing relies on, who wins the
ball from whom, and the passing patterns a team repeats.

Everything is computed from the validated events before `minute` (time-scoped like every other
view) and carries the event IDs it rests on. Headlines describe what happened; they never claim
why it happened.

Coordinates: x is attack-relative (each team attacks towards 100). y is shared by both teams, so a
team's left depends on the team: for the home side the left is high y, for the away side low y.
Points returned here are in the attacking team's view (`ay` high = their left).
"""
from __future__ import annotations
from collections import Counter, defaultdict
from typing import Any

import networkx as nx

from .core import Event
from .squads import CLUBS, PLAYERS

FINAL_THIRD = 200 / 3
CHANNELS = ('left', 'centre', 'right')
_CHANNEL_WORDS = {'left': 'down the left', 'centre': 'through the centre', 'right': 'down the right'}
_TOWARDS = {'left': 'to the left', 'centre': 'into the centre', 'right': 'to the right'}


def _name(pid: str | None) -> str:
    return PLAYERS[pid].name if pid in PLAYERS else (pid or 'unknown')


def _club(team: str) -> str:
    return CLUBS[team].short


def _clock(e: Event) -> int:
    return e.minute * 60 + e.second


def _evidence(e: Event) -> dict[str, Any]:
    return {'id': e.event_id, 'clock': _clock(e), 'player': _name(e.player_id), 'type': e.event_type,
            'to': _name(e.recipient_player_id) if e.recipient_player_id else None}


def _ay(team: str, y: float) -> float:
    """y in the attacking team's view: high is their left."""
    return y if team == 'home' else 100 - y


def channel(team: str, y: float) -> str:
    ay = _ay(team, y)
    return 'left' if ay >= FINAL_THIRD else 'right' if ay < 100 / 3 else 'centre'


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


# --- Where they attack ----------------------------------------------------------------------------

def zones(events: list[Event], team: str, minute: int, window: int = 15) -> dict[str, Any]:
    """Completed passes into or within the final third, by channel: so far, and the last `window`
    minutes against everything before them."""
    visible = [e for e in events if e.minute < minute]
    attacks = [e for e in visible if e.team_id == team and e.event_type == 'pass' and e.outcome == 'success'
               and e.end_x is not None and e.end_y is not None and e.end_x >= FINAL_THIRD]
    split = max(0, minute - window)
    recent = [e for e in attacks if e.minute >= split]
    before = [e for e in attacks if e.minute < split]
    out: dict[str, Any] = {}
    for ch in CHANNELS:
        all_ch = [e for e in attacks if channel(team, e.end_y) == ch]
        out[ch] = {'passes': len(all_ch), 'share': _pct(len(all_ch), len(attacks)),
                   'recent_share': _pct(sum(channel(team, e.end_y) == ch for e in recent), len(recent)),
                   'before_share': _pct(sum(channel(team, e.end_y) == ch for e in before), len(before)),
                   'event_ids': [e.event_id for e in all_ch][-40:]}
    club = _club(team)
    headline = None
    if len(recent) >= 6 and len(before) >= 6:
        ch = max(CHANNELS, key=lambda c: out[c]['recent_share'] - out[c]['before_share'])
        rise = out[ch]['recent_share'] - out[ch]['before_share']
        if rise >= 15:
            headline = (f"{club}'s attacks moved {_TOWARDS[ch]}: {out[ch]['recent_share']}% of their final-third passes "
                        f"in the last {window} minutes, up from {out[ch]['before_share']}% before.")
    if headline is None and attacks:
        ch = max(CHANNELS, key=lambda c: out[c]['passes'])
        how = 'mostly' if out[ch]['share'] >= 50 else 'most often'
        headline = f"{club} attack {how} {_CHANNEL_WORDS[ch]}: {out[ch]['share']}% of their final-third passes so far."
    points = [{'x': e.end_x, 'ay': round(_ay(team, e.end_y), 1), 'channel': channel(team, e.end_y),
               'recent': e.minute >= split, 'id': e.event_id} for e in attacks][-200:]
    return {'team': team, 'minute': minute, 'window': window, 'final_third_passes': len(attacks),
            'recent_passes': len(recent), 'channels': out, 'points': points,
            'headline': headline or f'{club} have no completed passes in the final third yet.',
            'evidence': [_evidence(e) for e in attacks[-12:]]}


# --- Roles over time ------------------------------------------------------------------------------

def _context(events: list[Event], team: str, end: int) -> str:
    """The team's latest substitution, or either side's red card, in the ten minutes before `end`, as
    plain timing context (it says what came first, never that it caused the change)."""
    recent = [e for e in events if end - 10 <= e.minute < end and (
        (e.event_type == 'substitution' and e.team_id == team)
        or (e.event_type == 'card' and e.outcome in ('red', 'second_yellow')))]
    if not recent:
        return ''
    e = recent[-1]
    if e.event_type == 'substitution':
        return f" This followed {_club(e.team_id)}'s {e.minute + 1}′ substitution ({_name(e.replacement_player_id)} for {_name(e.player_id)})."
    return f" This followed {_name(e.player_id)}'s red card ({_club(e.team_id)}, {e.minute + 1}′)."


def role_timeline(g: nx.MultiDiGraph, events: list[Event], team: str, minute: int,
                  step: int = 5, window: int = 15, min_passes: int = 10) -> dict[str, Any]:
    """The hub and key link of each rolling `window`-minute spell, every `step` minutes, and each
    change of role holder with its timing context and the passes behind it."""
    from .knowledge import network_roles, passing_graph
    spells = []
    for end in range(step, minute + 1, step):
        start = max(0, end - window)
        r = network_roles(g, team, start, end)
        enough = r.get('completed_passes', 0) >= min_passes
        spells.append({'start': start, 'end': end, 'passes': r.get('completed_passes', 0),
                       'hub': r.get('hub') if enough else None, 'key_link': r.get('connector') if enough else None})
    changes = []
    for role, label in (('hub', 'the hub'), ('key_link', 'the key link')):
        # A change counts only when the new holder keeps the role for two spells running, so a
        # one-spell wobble is not reported as a change.
        held = None
        for i in range(len(spells) - 1):
            b = spells[i][role]
            if not b or spells[i + 1][role] != b or b == held:
                continue
            a, held = held, b
            if a is not None:
                cur = spells[i]
                net = passing_graph(g, team, cur['start'], cur['end'])
                ids = [x for u, v, d in net.edges(data=True) if b in (u, v) for x in d['event_ids']]
                changes.append({'minute': cur['end'], 'role': role, 'from': a, 'to': b,
                                'text': f"{_name(b)} took over from {_name(a)} as {label} "
                                        f"({cur['start']}–{cur['end']}′).{_context(events, team, cur['end'])}",
                                'event_ids': sorted(ids)[-30:]})
    changes.sort(key=lambda c: (c['minute'], c['role']))
    # One player taking both roles in the same spell is one change, not two.
    merged: list[dict[str, Any]] = []
    for c in changes:
        last = merged[-1] if merged else None
        if last and last['minute'] == c['minute'] and last['to'] == c['to'] and last['role'] != c['role']:
            hub, key = (last, c) if last['role'] == 'hub' else (c, last)
            frm = (f"from {_name(hub['from'])}" if hub['from'] == key['from']
                   else f"from {_name(hub['from'])} and {_name(key['from'])}")
            start = c['text'][c['text'].rindex('(') + 1:].split('–')[0]
            last.update({'role': 'both', 'from': [hub['from'], key['from']],
                         'event_ids': sorted(set(last['event_ids'] + c['event_ids']))[-30:],
                         'text': f"{_name(c['to'])} took over as both the hub and the key link, {frm} "
                                 f"({start}–{c['minute']}′).{_context(events, team, c['minute'])}"})
        else:
            merged.append(c)
    changes = merged
    holders: dict[str, dict[str, list[list[int]]]] = defaultdict(lambda: {'hub': [], 'key_link': []})
    for s in spells:
        for role in ('hub', 'key_link'):
            if s[role]:
                holders[s[role]][role].append([s['end'] - step, s['end']])
    club = _club(team)
    if changes:
        headline = changes[-1]['text'].split(' This followed')[0]
    else:
        hubs = [s['hub'] for s in spells if s['hub']]
        headline = (f"{_name(hubs[-1])} has been {club}'s hub throughout." if hubs and len(set(hubs)) == 1
                    else f'Not enough completed passes yet to read {club}\'s roles.')
    return {'team': team, 'minute': minute, 'step': step, 'window': window, 'spells': spells, 'changes': changes,
            'players': [{'player': p, 'name': _name(p), **v} for p, v in holders.items()], 'headline': headline}


# --- Who they rely on -----------------------------------------------------------------------------

def _efficiency(net: nx.DiGraph, players: list[str], without: str | None = None) -> float:
    """How well connected the passing network is: the average, over ordered pairs of `players`, of
    1 / (shortest path length), where a lane used n times has length 1/n. Unreachable pairs count 0."""
    h = net if without is None else net.subgraph([n for n in net if n != without])
    pairs = [(a, b) for a in players for b in players if a != b]
    if not pairs:
        return 0.0
    total = 0.0
    for a in players:
        if a not in h:
            continue
        lengths = nx.single_source_dijkstra_path_length(h, a, weight='length')
        total += sum(1 / lengths[b] for b in players if b != a and b in lengths and lengths[b] > 0)
    return total / len(pairs)


def dependency(g: nx.MultiDiGraph, team: str, start: int, end: int, min_passes: int = 2) -> dict[str, Any]:
    """For each player: the share of the team's completed passes that involved them, and how much less
    connected the passing network is without them (weighted global efficiency over the other players,
    with and without them). Plus the team's passing units (Louvain communities)."""
    from .knowledge import average_positions, passing_graph
    full = passing_graph(g, team, start, end)
    net = nx.DiGraph()
    for u, v, d in full.edges(data=True):
        net.add_edge(u, v, weight=d['weight'], length=1 / d['weight'], event_ids=d['event_ids'])
    total = sum(d['weight'] for _, _, d in net.edges(data=True))
    players = []
    for p in net.nodes:
        others = [n for n in net.nodes if n != p]
        before, after = _efficiency(net, others), _efficiency(net, others, without=p)
        involved = sum(d['weight'] for u, v, d in net.edges(data=True) if p in (u, v))
        players.append({'player': p, 'name': _name(p), 'share': _pct(round((before - after) * 1000), round(before * 1000)),
                        'pass_share': _pct(involved, total)})
    players.sort(key=lambda r: (-r['share'], -r['pass_share'], r['name']))
    shown = nx.DiGraph()
    for u, v, d in net.edges(data=True):
        if d['weight'] >= min_passes:
            shown.add_edge(u, v, **d)
    units: list[list[str]] = []
    if shown.number_of_edges():
        und = nx.Graph()
        for u, v, d in shown.edges(data=True):
            w = und[u][v]['weight'] + d['weight'] if und.has_edge(u, v) else d['weight']
            und.add_edge(u, v, weight=w)
        units = [sorted(c) for c in nx.community.louvain_communities(und, weight='weight', seed=7) if len(c) > 1]
        units.sort(key=lambda c: (-len(c), c))
    positions = average_positions(g, team, start, end)
    nodes = [{'player': p, 'name': _name(p), 'shirt': PLAYERS[p].shirt if p in PLAYERS else None,
              'x': positions.get(p, {}).get('x', 50), 'ay': round(_ay(team, positions.get(p, {}).get('y', 50)), 1),
              'unit': next((i for i, c in enumerate(units) if p in c), None)} for p in net.nodes]
    edges = [{'from': u, 'to': v, 'passes': d['weight'], 'event_ids': d['event_ids'][-10:]}
             for u, v, d in shown.edges(data=True)]
    club = _club(team)
    top = players[0] if players else None
    if top and top['share'] >= 15:
        headline = (f"{club}'s passing leans most on {top['name']}: {top['pass_share']}% of their passes involved them, "
                    f"and their network is {top['share']}% less connected without them.")
    elif top:
        headline = (f"{club}'s passing is spread out; it leans most on {top['name']}: {top['pass_share']}% of their "
                    f"passes involved them, and the network is {top['share']}% less connected without them.")
    else:
        headline = f'Not enough completed passes yet to map {club}\'s network.'
    return {'team': team, 'window': [start, end], 'min_passes': min_passes, 'passes': total,
            'players': players, 'nodes': nodes, 'edges': edges,
            'units': [[{'player': p, 'name': _name(p)} for p in c] for c in units], 'headline': headline}


# --- Who wins the ball from whom ------------------------------------------------------------------

def duels(events: list[Event], team: str, minute: int) -> dict[str, Any]:
    """Each tackle or recovery by `team` straight after an opponent's action: the opponent it won
    the ball from, and where (in the winning team's attacking view)."""
    visible = [e for e in events if e.minute < minute]
    pairs: dict[tuple[str, str], list[Event]] = defaultdict(list)
    wins: list[Event] = []
    for prev, e in zip(visible, visible[1:]):
        if e.team_id == team and e.event_type in ('tackle', 'recovery') and prev.team_id != team:
            pairs[(e.player_id, prev.player_id)].append(e)
            wins.append(e)
    top = sorted(pairs.items(), key=lambda kv: (-len(kv[1]), _name(kv[0][0])))[:8]
    by_player = Counter(e.player_id for e in wins)
    high = [e for e in wins if e.x >= 50]
    club = _club(team)
    if top and len(top[0][1]) >= 2:
        (w, l), evs = top[0]
        times = 'twice' if len(evs) == 2 else f'{len(evs)} times'
        headline = f"{_name(w)} won the ball from {_name(l)} {times}."
    elif wins:
        p, n = by_player.most_common(1)[0]
        headline = f"{club} won the ball back {len(wins)} times; {_name(p)} most often ({n})."
    else:
        headline = f'{club} have not won the ball back from an opponent yet.'
    return {'team': team, 'minute': minute, 'won': len(wins), 'won_in_opponent_half': len(high),
            'pairs': [{'winner': w, 'winner_name': _name(w), 'loser': l, 'loser_name': _name(l), 'count': len(evs),
                       'event_ids': [e.event_id for e in evs],
                       'points': [{'x': e.x, 'ay': round(_ay(team, e.y), 1)} for e in evs]} for (w, l), evs in top],
            'players': [{'player': p, 'name': _name(p), 'won': n} for p, n in by_player.most_common(6)],
            'points': [{'x': e.x, 'ay': round(_ay(team, e.y), 1), 'id': e.event_id} for e in wins][-120:],
            'headline': headline}


# --- Patterns they repeat -------------------------------------------------------------------------

def patterns(events: list[Event], team: str, minute: int, min_count: int = 3, limit: int = 6) -> dict[str, Any]:
    """Three-player passing moves (A to B, then B to C, inside one possession) that a team repeats,
    and how many of the possessions they appeared in ended in a shot or a goal."""
    visible = [e for e in events if e.minute < minute]
    by_possession: dict[str, list[Event]] = defaultdict(list)
    for e in visible:
        by_possession[e.possession_id].append(e)
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for pid, evs in by_possession.items():
        passes = [e for e in evs if e.team_id == team and e.event_type == 'pass']
        shot = any(e.team_id == team and e.event_type == 'shot' for e in evs)
        goal = any(e.team_id == team and e.event_type == 'shot' and e.outcome == 'goal' for e in evs)
        found = set()
        for a, b in zip(passes, passes[1:]):
            if a.outcome == 'success' and b.outcome == 'success' and a.recipient_player_id == b.player_id \
                    and b.recipient_player_id:
                move = (a.player_id, b.player_id, b.recipient_player_id)
                if move in found:
                    continue
                found.add(move)
                m = seen.setdefault(move, {'count': 0, 'shots': 0, 'goals': 0, 'event_ids': []})
                m['count'] += 1
                m['shots'] += shot
                m['goals'] += goal
                m['event_ids'] += [a.event_id, b.event_id]
    ranked = sorted(((k, v) for k, v in seen.items() if v['count'] >= min_count),
                    key=lambda kv: (-kv[1]['count'], -kv[1]['shots'], kv[0]))[:limit]
    moves = [{'players': list(k), 'names': [_name(p) for p in k], 'one_two': k[0] == k[2],
              'count': v['count'], 'shots': v['shots'],
              'goals': v['goals'], 'event_ids': v['event_ids'][-20:]} for k, v in ranked]
    club = _club(team)
    if moves:
        m = moves[0]
        ended = 'none ending in a shot' if not m['shots'] else f"{m['shots']} ending in a shot"
        what = (f"the one-two between {m['names'][0]} and {m['names'][1]}" if m['one_two']
                else ' → '.join(m['names']))
        headline = f"{club}'s most repeated move: {what}, {m['count']} times, {ended}."
    else:
        headline = f'{club} have not repeated a three-player move {min_count} times yet.'
    return {'team': team, 'minute': minute, 'min_count': min_count, 'moves': moves, 'headline': headline}


def structure(g: nx.MultiDiGraph, events: list[Event], team: str, minute: int) -> dict[str, Any]:
    """All five views for one team at `minute`, plus a readable entry for every event they cite."""
    out = {'zones': zones(events, team, minute), 'roles': role_timeline(g, events, team, minute),
           'dependency': dependency(g, team, 0, minute), 'duels': duels(events, team, minute),
           'patterns': patterns(events, team, minute)}
    cited = {i for c in out['zones']['channels'].values() for i in c['event_ids']}
    cited |= {i for c in out['roles']['changes'] for i in c['event_ids']}
    cited |= {i for e in out['dependency']['edges'] for i in e['event_ids']}
    cited |= {i for p in out['duels']['pairs'] for i in p['event_ids']}
    cited |= {i for m in out['patterns']['moves'] for i in m['event_ids']}
    by_id = {e.event_id: e for e in events}
    out['events'] = {i: _evidence(by_id[i]) for i in sorted(cited) if i in by_id}
    return out
