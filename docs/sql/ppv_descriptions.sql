-- Polished PPV descriptions for the Events pages (same meaning as the originals, with
-- typos fixed and full sentences). Run with the RDS admin account.

UPDATE PPV SET Description = 'An 8-fighter Royal Rumble (it started with 4). The winner earns the main event at Brawlmania.' WHERE PPV_Name = 'Royal Rumble';
UPDATE PPV SET Description = 'Poké Ball matches: items on high, and Poké Balls are the only item.' WHERE PPV_Name = 'Pokeslam';
UPDATE PPV SET Description = 'Every match is 5 stock, and the Smash Bros. Championship is on the line for bragging rights.' WHERE PPV_Name = 'Brawlmania';
UPDATE PPV SET Description = 'A 6-fighter match for each brand (it started with 4). The first to two finishes wins the briefcase, which can be cashed in on any champion at any time.' WHERE PPV_Name = 'Money in the Bank';
UPDATE PPV SET Description = 'Standard matches, with the draft right after.' WHERE PPV_Name = 'Ignition';
UPDATE PPV SET Description = 'Standard matches.' WHERE PPV_Name = 'Summer Slam';
UPDATE PPV SET Description = 'Each brand holds a tournament to decide its champion. Seeds are set during the month, with the champion as the 1 seed.' WHERE PPV_Name = 'Final Destination Tournament';
UPDATE PPV SET Description = 'Every match is a triple threat or a fatal 4-way.' WHERE PPV_Name = 'The Great Race';
UPDATE PPV SET Description = 'Standard matches (it used to be all 1-stock matches).' WHERE PPV_Name = 'King of the Hill';
UPDATE PPV SET Description = 'Discontinued. Every fighter started with a 100% handicap.' WHERE PPV_Name = 'Full Contact';
UPDATE PPV SET Description = 'Contenders start with a 50% handicap.' WHERE PPV_Name = 'Championship Cruise';
UPDATE PPV SET Description = 'A 5-fighter gauntlet for the major titles, in random order.' WHERE PPV_Name = 'Championship Scramble';
UPDATE PPV SET Description = 'Discontinued. Each match had 3 options, and the other side picked which one was used.' WHERE PPV_Name = 'Cyber Sunday';
UPDATE PPV SET Description = 'Two fighters from each brand face off in a 2 vs. 2 vs. 2 tag team match.' WHERE PPV_Name = 'Smash Series';
