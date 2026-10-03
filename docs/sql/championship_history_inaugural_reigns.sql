-- ChampionshipHistory: count inaugural champions of every title, not only Season 1's.
--
-- Before: inaugural champions (awarded a title, then flagged as defending in its first fight)
-- were only recognised in Season 1 Month 1. The titles that debuted in S6 M1 (Ultimate, Monster,
-- Chaos) lost their inaugural reigns: Mr Game & Watch (Ultimate), Lucas (Monster), Greninja (Chaos).
--
-- After: in each championship's first-ever fight, its defending champion gets a reign, win or lose.
-- Verified read-only against the live view: the same 204 rows plus exactly those 3 reigns.
-- New titles in future seasons are handled automatically.
--
-- Run with the RDS admin account (the app's logins can't alter views).

CREATE OR REPLACE
ALGORITHM = UNDEFINED VIEW `ChampionshipHistory` AS
select
    `r`.`Fighter_Name` AS `Fighter_Name`,
    `c`.`Championship_Name` AS `Championship_Name`,
    `c`.`championship_tier` AS `Championship_Tier`,
    (case
        when (((lead((case when (`f`.`Season_ID` = 1) then `f`.`Month` when (`f`.`Season_ID` = 2) then (`f`.`Month` + 12) when (`f`.`Season_ID` = 3) then (`f`.`Month` + 24) when (`f`.`Season_ID` = 4) then (`f`.`Month` + 36) when (`f`.`Season_ID` = 5) then (`f`.`Month` + 48) when (`f`.`Season_ID` = 6) then (`f`.`Month` + 60) when (`f`.`Season_ID` = 7) then (`f`.`Month` + 72) when (`f`.`Season_ID` = 8) then (`f`.`Month` + 84) end)) OVER (PARTITION BY `c`.`Championship_ID` ORDER BY `r`.`Result_ID`) - (case when (`f`.`Season_ID` = 1) then `f`.`Month` when (`f`.`Season_ID` = 2) then (`f`.`Month` + 12) when (`f`.`Season_ID` = 3) then (`f`.`Month` + 24) when (`f`.`Season_ID` = 4) then (`f`.`Month` + 36) when (`f`.`Season_ID` = 5) then (`f`.`Month` + 48) when (`f`.`Season_ID` = 6) then (`f`.`Month` + 60) when (`f`.`Season_ID` = 7) then (`f`.`Month` + 72) when (`f`.`Season_ID` = 8) then (`f`.`Month` + 84) end)) is null) and (`f`.`Season_ID` = 1)) then 1
        when (`c`.`Championship_ID` = 11) then (lead((case when (`f`.`Season_ID` = 1) then `f`.`Month` when (`f`.`Season_ID` = 2) then (`f`.`Month` + 12) when (`f`.`Season_ID` = 3) then (`f`.`Month` + 24) when (`f`.`Season_ID` = 4) then (`f`.`Month` + 36) when (`f`.`Season_ID` = 5) then (`f`.`Month` + 48) when (`f`.`Season_ID` = 6) then (`f`.`Month` + 60) when (`f`.`Season_ID` = 7) then (`f`.`Month` + 72) when (`f`.`Season_ID` = 8) then (`f`.`Month` + 84) end), 2) OVER (PARTITION BY `c`.`Championship_ID` ORDER BY `r`.`Result_ID`) - (case when (`f`.`Season_ID` = 1) then `f`.`Month` when (`f`.`Season_ID` = 2) then (`f`.`Month` + 12) when (`f`.`Season_ID` = 3) then (`f`.`Month` + 24) when (`f`.`Season_ID` = 4) then (`f`.`Month` + 36) when (`f`.`Season_ID` = 5) then (`f`.`Month` + 48) when (`f`.`Season_ID` = 6) then (`f`.`Month` + 60) when (`f`.`Season_ID` = 7) then (`f`.`Month` + 72) when (`f`.`Season_ID` = 8) then (`f`.`Month` + 84) end))
        else (lead((case when (`f`.`Season_ID` = 1) then `f`.`Month` when (`f`.`Season_ID` = 2) then (`f`.`Month` + 12) when (`f`.`Season_ID` = 3) then (`f`.`Month` + 24) when (`f`.`Season_ID` = 4) then (`f`.`Month` + 36) when (`f`.`Season_ID` = 5) then (`f`.`Month` + 48) when (`f`.`Season_ID` = 6) then (`f`.`Month` + 60) when (`f`.`Season_ID` = 7) then (`f`.`Month` + 72) when (`f`.`Season_ID` = 8) then (`f`.`Month` + 84) end)) OVER (PARTITION BY `c`.`Championship_ID` ORDER BY `r`.`Result_ID`) - (case when (`f`.`Season_ID` = 1) then `f`.`Month` when (`f`.`Season_ID` = 2) then (`f`.`Month` + 12) when (`f`.`Season_ID` = 3) then (`f`.`Month` + 24) when (`f`.`Season_ID` = 4) then (`f`.`Month` + 36) when (`f`.`Season_ID` = 5) then (`f`.`Month` + 48) when (`f`.`Season_ID` = 6) then (`f`.`Month` + 60) when (`f`.`Season_ID` = 7) then (`f`.`Month` + 72) when (`f`.`Season_ID` = 8) then (`f`.`Month` + 84) end))
    end) AS `months_held`,
    `f`.`Season_ID` AS `Season_Won`,
    `f`.`Month` AS `Month_Won`,
    (case when (`c`.`Championship_ID` = 11) then lead(`f`.`Season_ID`, 2) OVER (PARTITION BY `c`.`Championship_ID` ORDER BY `r`.`Result_ID`) else lead(`f`.`Season_ID`) OVER (PARTITION BY `c`.`Championship_ID` ORDER BY `r`.`Result_ID`) end) AS `Season_Lost`,
    (case when (`c`.`Championship_ID` = 11) then lead(`f`.`Month`, 2) OVER (PARTITION BY `c`.`Championship_ID` ORDER BY `r`.`Result_ID`) else lead(`f`.`Month`) OVER (PARTITION BY `c`.`Championship_ID` ORDER BY `r`.`Result_ID`) end) AS `Month_Lost`
from
    (((`Results` `r`
join `Fight` `f` on ((`f`.`Fight_ID` = `r`.`Fight_ID`)))
join `Championship` `c` on ((`c`.`Championship_ID` = `f`.`Championship_ID`)))
-- Each championship's first-ever fight. Its defending champion is the inaugural
-- champion (awarded the title, not won in a fight), whether they won or lost.
join (select `Championship_ID`, min(`Fight_ID`) AS `Debut_Fight_ID`
      from `Fight` where `Championship_ID` is not null group by `Championship_ID`) `d`
    on ((`d`.`Championship_ID` = `f`.`Championship_ID`)))
where
    (
        -- A challenger wins the title
        ((`r`.`Decision` = 'W') and ((`r`.`DefendingIndicator` = '') or (`r`.`Result_ID` = 2498)))
        -- Inaugural champions: the winner, or the defending champion, of a title's first fight
        or ((`f`.`Fight_ID` = `d`.`Debut_Fight_ID`) and ((`r`.`Decision` = 'W') or (`r`.`DefendingIndicator` = 'y')))
        -- Smash Bros.: every winner is a new holder
        or ((`f`.`Championship_ID` = 10) and (`r`.`Decision` = 'W'))
    )
order by `c`.`Championship_Name`, `r`.`Result_ID`;
