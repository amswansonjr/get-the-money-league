"""Awards derived from saved historical lineups and league-scored projections."""
from decimal import Decimal, ROUND_HALF_UP
import math

POSITIONS = ('QB', 'RB', 'WR', 'TE', 'DEF')
FLEX = {'FLEX': {'RB','WR','TE'}, 'SUPER_FLEX': {'QB','RB','WR','TE'}, 'REC_FLEX': {'WR','TE'}, 'WRRB_FLEX': {'WR','RB'}}

def cents(value):
    if not isinstance(value, (int,float)) or not math.isfinite(value):
        raise ValueError('Missing or invalid points')
    return int(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)*100)

def actual(row):
    return row['custom_points'] if row.get('custom_points') is not None else row['points']

def positions(player):
    return set(player.get('fantasy_positions') or [player.get('position')])

def optimal(row, players, slots):
    states = {0: 0}
    for pid in row.get('players') or []:
        if pid == '0': continue
        if pid not in row.get('players_points', {}) or pid not in players:
            raise ValueError('Missing historical player points or eligibility')
        points = cents(row['players_points'][pid]); updated = dict(states)
        for mask, total in states.items():
            for i, slot in enumerate(slots):
                if not mask & (1<<i) and positions(players[pid]) & FLEX.get(slot, {slot}):
                    key = mask | (1<<i)
                    updated[key] = max(updated.get(key, -10**12), total+points)
        states = updated
    full = (1<<len(slots))-1
    if full not in states: raise ValueError('Cannot fill all starting slots')
    return states[full]

def projection_total(row, projection_index, scoring):
    total = 0
    for pid in row.get('starters') or []:
        if pid == '0': continue
        record = projection_index.get(pid)
        if not record or record.get('stats', {}).get('gp', 0) <= 0:
            raise ValueError('Missing weekly starter projection')
        stats = record['stats']
        # Match the per-player, two-decimal scoring that reconciles with the saved report.
        value = sum(stats.get(k,0)*round(weight,6) for k,weight in scoring.items())
        total += cents(round(value,2))
    if total <= 0: raise ValueError('Nonpositive projected team total')
    return total

def extra_awards(data, directory, week, warnings):
    rows = data[f'week_{week}']; players = data['players']; league = data['league']
    slots = [s for s in league['roster_positions'] if s not in ('BN','IR','TAXI')]
    generated = []; efficiencies = []; projected = []
    for row in rows:
        mid = directory[row['roster_id']]['managerId']
        try:
            starter_total = sum(cents(row['players_points'][pid]) for pid in row['starters'] if pid!='0')
            if starter_total != cents(actual(row)): raise ValueError('Starter total differs from team score')
            possible = optimal(row, players, slots)
            if possible <= 0 or cents(actual(row)) > possible: raise ValueError('Invalid efficiency denominator or adjusted score')
            efficiencies.append((Decimal(cents(actual(row)))/possible, mid, actual(row), possible/100))
        except (ValueError, KeyError) as error:
            warnings.append(f'Week {week}: manager-efficiency awards withheld: {error}.')
    if len(efficiencies) == len(rows):
        for title, pick in [('Best Manager 🔥', max), ('Worst Manager 🤔', min)]:
            target = pick(e[0] for e in efficiencies)
            tied = [e for e in efficiencies if e[0]==target]
            # Highest actual points breaks a best-efficiency tie; worst-efficiency ties are shared.
            if pick is max: tied = [e for e in tied if e[2]==max(t[2] for t in tied)]
            for ratio, mid, points, possible in tied:
                generated.append({'title':title,'managerId':mid,'points':points,'description':f'{float(ratio*100):.2f}% lineup efficiency; {possible:.2f} possible points.','group':'team','source':'calculated_lineup','optimalPoints':possible,'efficiencyPercent':float(ratio*100)})
    records = data.get(f'projections_{week}', [])
    index = {}
    for record in records:
        pid = record['player_id']
        if pid in index: raise ValueError(f'Duplicate Week {week} player projection: {pid}')
        index[pid] = record
    try:
        for row in rows:
            total = projection_total(row,index,league['scoring_settings'])
            projected.append((Decimal(cents(actual(row)))/total-1, directory[row['roster_id']]['managerId'], actual(row), total/100))
        for title, pick in [('Overachiever 🤓',max), ('Below Expectation 💀',min)]:
            target = pick(e[0] for e in projected)
            for ratio, mid, points, total in projected:
                if ratio == target:
                    generated.append({'title':title,'managerId':mid,'points':points,'description':f'{float(ratio*100):+.2f}% versus {total:.2f} projected points.','group':'team','source':'calculated_projection','projectedPoints':total,'projectionChangePercent':float(ratio*100)})
    except (ValueError, KeyError) as error:
        warnings.append(f'Week {week}: projection awards unavailable: {error}. Other calculated awards remain available.')
    for group in ('starter','bench'):
        for position in POSITIONS:
            candidates=[]
            for row in rows:
                starters=set(row.get('starters') or [])
                for pid in row.get('players') or []:
                    if (pid in starters)!=(group=='starter'): continue
                    player=players.get(pid,{})
                    if position not in positions(player): continue
                    if pid not in row.get('players_points',{}):
                        raise ValueError(f'Week {week}: missing player points for position award')
                    name=player.get('full_name') or ' '.join(filter(None,[player.get('first_name'),player.get('last_name')]))
                    candidates.append((cents(row['players_points'][pid]), directory[row['roster_id']]['managerId'], name))
            if candidates:
                high=max(c[0] for c in candidates)
                for points,mid,name in candidates:
                    if points==high:
                        generated.append({'title':position+(' of the Week ⭐' if group=='starter' else ' Benchwarmer of the Week 👀'),'managerId':mid,'points':points/100,'description':name,'group':group,'source':'saved_lineup'})
    return generated
