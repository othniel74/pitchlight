"""Match structure: zones, roles over time, dependency, duels and patterns are time-scoped, rest on
real events of the right team, and describe without claiming causes."""
import pytest
from fastapi.testclient import TestClient

from app.core import generate_match
from app.knowledge import match_graph
from app.main import app
from app.structure import channel, dependency, duels, patterns, role_timeline, structure, zones

SEED = 20261020


@pytest.fixture(scope='module')
def match():
    g, events, _ = match_graph(SEED, 90)
    return g, events, {e.event_id: e for e in events}


def test_channels_are_seen_from_the_attacking_team():
    # The home side's left is high y; the away side's left is low y.
    assert channel('home', 90) == 'left' and channel('away', 90) == 'right'
    assert channel('home', 10) == 'right' and channel('away', 10) == 'left'
    assert channel('home', 50) == channel('away', 50) == 'centre'


def test_zones_count_only_the_teams_final_third_passes_before_the_minute(match):
    _, events, by_id = match
    z = zones(events, 'away', 60)
    shares = [z['channels'][c]['share'] for c in ('left', 'centre', 'right')]
    assert z['final_third_passes'] > 0 and abs(sum(shares) - 100) <= 2
    for c in ('left', 'centre', 'right'):
        for i in z['channels'][c]['event_ids']:
            e = by_id[i]
            assert e.team_id == 'away' and e.minute < 60 and e.end_x >= 200 / 3 and channel('away', e.end_y) == c


def test_role_changes_persist_and_name_real_holders(match):
    g, events, by_id = match
    r = role_timeline(g, events, 'home', 90)
    holders = {s[k] for s in r['spells'] for k in ('hub', 'key_link') if s[k]}
    for c in r['changes']:
        assert c['to'] in holders and 'took over' in c['text']
        assert all(by_id[i].team_id == 'home' for i in c['event_ids'])
        assert 'because' not in c['text'] and 'caused' not in c['text']  # timing context, never a cause
    assert len(r['changes']) < len(r['spells'])  # one-spell wobbles are not reported


def test_dependency_measures_how_much_less_connected_the_network_is_without_a_player(match):
    g, _, _ = match
    d = dependency(g, 'away', 0, 90)
    assert d['players'] and all(0 <= p['share'] <= 100 and 0 <= p['pass_share'] <= 100 for p in d['players'])
    assert d['players'] == sorted(d['players'], key=lambda p: (-p['share'], -p['pass_share'], p['name']))
    assert d['players'][0]['share'] > d['players'][-1]['share']  # it tells players apart
    unit_players = [p['player'] for u in d['units'] for p in u]
    assert len(unit_players) == len(set(unit_players))  # each player is in at most one unit
    assert all(e['passes'] >= d['min_passes'] for e in d['edges'])


def test_duels_pair_a_win_with_the_opponent_who_had_the_ball(match):
    _, events, by_id = match
    order = {e.event_id: i for i, e in enumerate(events)}
    d = duels(events, 'home', 90)
    assert d['won'] > 0
    for pair in d['pairs']:
        for i in pair['event_ids']:
            e, prev = by_id[i], events[order[i] - 1]
            assert e.team_id == 'home' and e.event_type in ('tackle', 'recovery') and e.player_id == pair['winner']
            assert prev.team_id == 'away' and prev.player_id == pair['loser']


def test_patterns_are_chained_passes_inside_one_possession(match):
    _, events, by_id = match
    p = patterns(events, 'away', 90)
    assert p['moves']
    for m in p['moves']:
        assert m['count'] >= p['min_count'] and m['shots'] <= m['count']
        a, b, c = m['players']
        assert m['one_two'] == (a == c)
        ids = m['event_ids']
        for first, second in zip(ids[::2], ids[1::2]):
            x, y = by_id[first], by_id[second]
            assert x.possession_id == y.possession_id and x.recipient_player_id == y.player_id


def test_nothing_after_the_minute_is_used():
    events = generate_match(SEED)
    g, _, _ = match_graph(SEED, 30)
    s = structure(g, events, 'away', 30)
    used = set(s['zones']['channels']['left']['event_ids'] + s['zones']['channels']['centre']['event_ids']
               + s['zones']['channels']['right']['event_ids'])
    used |= {i for pair in s['duels']['pairs'] for i in pair['event_ids']}
    used |= {i for m in s['patterns']['moves'] for i in m['event_ids']}
    minute = {e.event_id: e.minute for e in events}
    assert used and all(minute[i] < 30 for i in used)


def test_the_endpoint_follows_team_minute_and_match():
    with TestClient(app) as client:
        a = client.get('/api/graph/structure?team=away&minute=90').json()
        b = client.get('/api/graph/structure?team=home&minute=90&seed=20261036').json()
    assert set(a) >= {'context', 'zones', 'roles', 'dependency', 'duels', 'patterns'}
    assert a['zones']['team'] == 'away' and b['zones']['team'] == 'home'
    assert b['context']['match_id'] != a['context']['match_id']


def test_every_cited_event_has_a_readable_entry(match):
    g, events, by_id = match
    s = structure(g, events, 'home', 90)
    cited = {i for m in s['patterns']['moves'] for i in m['event_ids']} | {i for p in s['duels']['pairs'] for i in p['event_ids']}
    assert cited <= set(s['events'])
    for i, entry in s['events'].items():
        assert entry['clock'] == by_id[i].minute * 60 + by_id[i].second and entry['type'] == by_id[i].event_type
