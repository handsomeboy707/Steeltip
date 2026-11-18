-- Window ranking of individual current leg results, not an average player rating.
SELECT p.name,a.leg_id,a.rating,DENSE_RANK() OVER(PARTITION BY a.division_id ORDER BY a.rating DESC) division_rank
FROM accepted_results a JOIN players p ON p.id=a.player_id WHERE a.eligible=1;

-- Nested query excludes superseded reviews.
SELECT p.name,r.status,s.rating,s.cap,s.tolerance FROM reviews r
JOIN players p ON p.id=r.player_id JOIN snapshots s ON s.revision_id=r.revision_id AND s.player_id=r.player_id
WHERE r.status='pending' AND EXISTS(SELECT 1 FROM legs l WHERE l.accepted_revision=r.revision_id);

-- Aggregates read summaries. Compare outputs to MongoDB validated-visit expansion.
SELECT player_id,SUM(points) points,SUM(darts) darts,SUM(busts) busts,COUNT(*) legs
FROM accepted_results WHERE eligible=1 GROUP BY player_id ORDER BY player_id;
