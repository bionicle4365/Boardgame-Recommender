import { describe, test, expect } from 'vitest';

describe('BGG Collection Browser Filtering & Sorting Logic', () => {
    const mockGames = [
        {
            id: "1",
            name: "Catan",
            minPlayers: "3",
            maxPlayers: "4",
            playingTime: "90",
            bggRating: "7.1",
            userRating: "8.0",
            year: "1995",
            collectionStatus: "Owned"
        },
        {
            id: "2",
            name: "7 Wonders Duel",
            minPlayers: "2",
            maxPlayers: "2",
            playingTime: "30",
            bggRating: "8.1",
            userRating: "8.5",
            year: "2015",
            collectionStatus: "Owned, Previously Owned"
        },
        {
            id: "3",
            name: "Gloomhaven",
            minPlayers: "1",
            maxPlayers: "4",
            playingTime: "120",
            bggRating: "8.7",
            userRating: "9.5",
            year: "2017",
            collectionStatus: "Owned, Wishlist"
        },
        {
            id: "4",
            name: "Captain Sonar",
            minPlayers: "2",
            maxPlayers: "8",
            playingTime: "45",
            bggRating: "7.5",
            userRating: "7.0",
            year: "2016",
            collectionStatus: "Want to Play"
        }
    ];

    test('Filter by search query name matching (case-insensitive)', () => {
        const query = 'gloom';
        const filtered = mockGames.filter(g => g.name.toLowerCase().includes(query.toLowerCase()));
        expect(filtered.length).toBe(1);
        expect(filtered[0].name).toBe('Gloomhaven');
    });

    test('Filter by status with multi-select OR semantics', () => {
        const activeStatuses = ['Wishlist', 'Want to Play'];
        const filtered = mockGames.filter(g => {
            const status = g.collectionStatus || '';
            return activeStatuses.some(s => status.includes(s));
        });
        expect(filtered.length).toBe(2);
        const names = filtered.map(g => g.name);
        expect(names).toContain('Gloomhaven');
        expect(names).toContain('Captain Sonar');
    });

    test('Filter by player count (exact match 2 players)', () => {
        const minPlayersFilter = 2;
        const maxPlayersFilter = 2;
        const filtered = mockGames.filter(g => {
            const min = parseInt(g.minPlayers);
            const max = parseInt(g.maxPlayers);
            return min <= maxPlayersFilter && max >= minPlayersFilter;
        });
        expect(filtered.length).toBe(3); // 7 Wonders Duel, Gloomhaven (1-4), Captain Sonar (2-8)
        expect(filtered.map(g => g.name)).not.toContain('Catan');
    });

    test('Filter by player count with 8+ players cap', () => {
        const minPlayersFilter = 6;
        const maxPlayersFilter = 8; // represents 8+
        const filtered = mockGames.filter(g => {
            const max = parseInt(g.maxPlayers);
            if (maxPlayersFilter === 8) {
                return max >= minPlayersFilter;
            }
            return max >= minPlayersFilter;
        });
        expect(filtered.length).toBe(1);
        expect(filtered[0].name).toBe('Captain Sonar');
    });

    test('Filter by playing time range', () => {
        const playtimeValues = [15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210, 225, 240];
        const minIdx = 1; // 30m
        const maxIdx = 3; // 60m
        const minTime = playtimeValues[minIdx];
        const maxTime = playtimeValues[maxIdx];

        const filtered = mockGames.filter(g => {
            const time = parseInt(g.playingTime);
            return time >= minTime && time <= maxTime;
        });
        expect(filtered.length).toBe(2);
        expect(filtered.map(g => g.name)).toEqual(['7 Wonders Duel', 'Captain Sonar']);
    });

    test('Filter by user rating boundary', () => {
        const minRating = 8.0;
        const maxRating = 9.0;
        const filtered = mockGames.filter(g => {
            const rating = parseFloat(g.userRating);
            return rating >= minRating && rating <= maxRating;
        });
        expect(filtered.length).toBe(2);
        expect(filtered.map(g => g.name)).toEqual(['Catan', '7 Wonders Duel']);
    });

    test('Sorting by rating ascending and descending', () => {
        const sortedDesc = [...mockGames].sort((a, b) => parseFloat(b.userRating) - parseFloat(a.userRating));
        expect(sortedDesc[0].name).toBe('Gloomhaven');
        expect(sortedDesc[sortedDesc.length - 1].name).toBe('Captain Sonar');

        const sortedAsc = [...mockGames].sort((a, b) => parseFloat(a.userRating) - parseFloat(b.userRating));
        expect(sortedAsc[0].name).toBe('Captain Sonar');
        expect(sortedAsc[sortedAsc.length - 1].name).toBe('Gloomhaven');
    });
});
