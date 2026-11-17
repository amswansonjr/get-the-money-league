// Commentary is derived only from the selected saved results, never roster speculation.
function buildRecapBanter(recap,names){
  const fmt=n=>n.toFixed(2),standings=new Map(recap.standings.map(t=>[t.managerId,t]));
  const scores=recap.games.flatMap(g=>[g.scoreA,g.scoreB]);
  const high=Math.max(...scores),low=Math.min(...scores);
  const margins=recap.games.filter(g=>g.winner).map(g=>Math.abs(g.scoreA-g.scoreB));
  const widest=Math.max(...margins),tightest=Math.min(...margins);
  const wins=[
    'Take the W, screenshot the receipt, and pretend this was the plan all along.',
    'The group chat would like an apology. The standings will accept the win instead.',
    'A win and a fresh license to be absolutely insufferable in the chat.',
    'One more W for the record, one more unbearable week for everyone else.',
    'The scoreboard signed off on the trash talk. Unfortunately, we all have to hear it.',
    'Collected the win and immediately became a problem for the group chat.'
  ];
  const losses=[
    'The lineup was submitted. The competitive portion apparently was optional.',
    'That is a lot of checking the app for an outcome you could have hated just once.',
    'The scoreboard has requested that all excuses be submitted in writing.',
    'Another week of doing the math until the math became personally offensive.',
    'A full week of anticipation for a receipt nobody wants to frame.',
    'The postgame press conference has been replaced by staring at the ceiling.'
  ];
  return recap.games.map((g,index)=>{
    const margin=Math.abs(g.scoreA-g.scoreB),tied=!g.winner;
    const winnerA=g.winner===g.managerA;
    const headline=tied?'Nobody wins. Everybody complains.':
      margin===widest?'Stop the count. The damage is already done.':
      margin===tightest?'A win by a thread. Trash talk by the mile.':
      Math.max(g.scoreA,g.scoreB)===high?'The points department finally answered the phone.':
      margin>=30?'That was a matchup on paper.':
      Math.max(g.scoreA,g.scoreB)<recap.median?'Somebody had to win this thing.':
      ['Receipts printed. Excuses declined.','The group chat has entered the evidence.','Six days of confidence. One ugly receipt.'][(recap.week+index)%3];
    const lines=[[g.managerA,g.scoreA,g.managerB,g.scoreB],[g.managerB,g.scoreB,g.managerA,g.scoreA]].map(([id,score,other,otherScore])=>{
      const team=standings.get(id),opponent=standings.get(other);
      const label=`${team?.team||names.get(id)} (${names.get(id)})`;
      const opponentLabel=opponent?.team||names.get(other);
      let verdict;
      if(tied)verdict='A tie. All that refreshing, and neither side even earned exclusive complaining rights.';
      else if(id===g.winner){
        if(score===high)verdict='Weekly high score. For once, the loudest person in the chat can actually bring a receipt.';
        else if(margin===widest)verdict='Biggest win of the week. There are competitive matchups, and then there is whatever this demolition was.';
        else if(margin===tightest)verdict='Closest win of the week. A victory this narrow deserves a seat belt, not a victory parade.';
        else if(score<recap.median)verdict='Below the weekly median and still collecting a W. Send the schedule a thank-you card.';
        else verdict=wins[(recap.week+index)%wins.length];
      }else{
        if(score===low)verdict='Weekly low score. The floor was available, and this team brought a shovel.';
        else if(score>recap.median)verdict='Above the weekly median and still taking an L. A respectable score with absolutely no refund policy.';
        else if(margin===widest)verdict='Biggest loss of the week. At some point this stopped being a matchup and became a documentary.';
        else if(margin===tightest)verdict='Closest loss of the week. Just enough hope to make every last refresh feel like a personal attack.';
        else verdict=losses[(recap.week+index)%losses.length];
      }
      const result=tied?'T':id===g.winner?'W':'L';
      const receipt=`${result}: ${fmt(score)}–${fmt(otherScore)} against ${opponentLabel}${tied?'':`; margin ${fmt(margin)}`}.`;
      const record=team?` Now ${team.wins}–${team.losses}${team.ties?`–${team.ties}`:''}, No. ${team.rank} in the recap standings.`:'';
      return `${label} — ${receipt} ${verdict}${record}`;
    });
    return {headline:`${index+1}. ${headline}`,lines};
  });
}
