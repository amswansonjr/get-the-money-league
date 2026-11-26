"""Add records and verified starter projections to a saved matchup snapshot."""
from calculated_awards import projection_total

def enrich(snapshot,data,directory):
    index={r['player_id']:r for r in data.get(f'projections_{snapshot["week"]}',[])}
    lineups={r['roster_id']:r for r in data.get(f'week_{snapshot["week"]}',[])}
    by_manager={t['managerId']:(rid,t) for rid,t in directory.items()}
    for match in snapshot['matches']:
        for team in match['teams']:
            rid,standing=by_manager[team['managerId']]
            team['record']=f'{standing["wins"]}–{standing["losses"]}'+(f'–{standing["ties"]}' if standing['ties'] else '')
            team['projectedPoints']=None
            if snapshot['status']=='upcoming':
                try:team['projectedPoints']=projection_total(lineups[rid],index,data['league']['scoring_settings'])/100
                except (ValueError,KeyError):pass
    return snapshot
