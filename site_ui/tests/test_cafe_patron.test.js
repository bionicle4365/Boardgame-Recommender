import { describe, test, expect, beforeEach } from 'vitest';
import fs from 'fs';
import path from 'path';

// Setup environment and load utils.js & cafe.js
const utilsJsPath = path.resolve(__dirname, '../assets/js/utils.js');
let rawUtilsCode = fs.readFileSync(utilsJsPath, 'utf8');

// Strip frontmatter and inject PLACEHOLDER_API_URL for mock mode
let utilsCode = rawUtilsCode.replace(/^---[\s\S]*?---/, '');
utilsCode = utilsCode.replace(/"\{\{\s*site\.cognito_client_id\s*\}\}"/g, '"mock-client-id"');
utilsCode = utilsCode.replace(/"\{\{\s*site\.cognito_region\s*\}\}"/g, '"us-east-1"');
utilsCode = utilsCode.replace(/"\{\{\s*site\.api_url\s*\}\}"/g, '"PLACEHOLDER_API_URL"');
eval(utilsCode);

const cafeJsPath = path.resolve(__dirname, '../assets/js/cafe.js');
const rawCafeCode = fs.readFileSync(cafeJsPath, 'utf8');
eval(rawCafeCode);

describe('Cafe Patron Portal & Vibe Check Client Logic', () => {
    beforeEach(() => {
        localStorage.clear();
        sessionStorage.clear();
        document.body.innerHTML = `
            <div id="cafe-patron-view">
                <div id="vibe-quiz-form"></div>
                <div id="venue-name-title"></div>
                <div id="venue-tagline"></div>
                <div id="header-table-badge"></div>
                <span id="cta-table-num"></span>
                <div id="header-wifi-chip" style="display: none;">
                    <span id="wifi-ssid-label"></span>
                    <span id="wifi-pass-label"></span>
                </div>
                <div id="cafe-view-switcher">
                    <button id="tab-btn-collection" class="active"></button>
                    <button id="tab-btn-recommender"></button>
                    <span id="collection-count-badge"></span>
                </div>
                <div id="cafe-collection-view">
                    <button id="btn-launch-recommender"></button>
                    <input id="cafe-search-input">
                    <button id="cafe-search-clear" style="display: none;"></button>
                    <div id="collection-quick-filters">
                        <button class="cafe-filter-chip active" data-filter="all"></button>
                        <button class="cafe-filter-chip" data-filter="2p"></button>
                        <button class="cafe-filter-chip" data-filter="4p"></button>
                        <button class="cafe-filter-chip" data-filter="shelved"></button>
                    </div>
                    <span id="collection-results-count"></span>
                    <select id="collection-sort-select">
                        <option value="name_asc">Name (A-Z)</option>
                        <option value="rating_desc">Highest Rated</option>
                    </select>
                    <div id="cafe-collection-grid"></div>
                </div>
                <div id="cafe-recommender-view" style="display: none;">
                    <button id="btn-back-to-library"></button>
                    <div id="vibe-quiz-card"></div>
                    <div id="results-section" style="display: none;">
                        <span id="results-table-num"></span>
                        <button id="btn-back-from-results"></button>
                        <div id="cafe-results-container"></div>
                    </div>
                </div>
                <button id="quiz-submit-btn"></button>
            </div>
        `;
    });

    test('parseVenueContext extracts cafe and table from URL search params', () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/?cafe=maltandmeeple&table=5');

        window.CafePortal.parseVenueContext();
        expect(window.CafePortal.state.cafeId).toBe('maltandmeeple');
        expect(window.CafePortal.state.table).toBe('5');
        expect(sessionStorage.getItem('cafe_patron_cafe_id')).toBe('maltandmeeple');
        expect(sessionStorage.getItem('cafe_patron_table')).toBe('5');
    });

    test('parseVenueContext extracts cafe from URL path segment /cafe/:slug', () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/the-dice-box-cafe?table=12');

        const hasVenue = window.CafePortal.parseVenueContext();
        expect(hasVenue).toBe(true);
        expect(window.CafePortal.state.cafeId).toBe('the-dice-box-cafe');
        expect(window.CafePortal.state.table).toBe('12');
    });

    test('parseVenueContext returns false and leaves state empty when visiting /cafe/ with no params', () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/');

        const hasVenue = window.CafePortal.parseVenueContext();
        expect(hasVenue).toBe(false);
        expect(window.CafePortal.state.cafeId).toBe('');
        expect(window.CafePortal.state.table).toBe('');
    });

    test('loadVenueMetadata populates venue branding and Wi-Fi credentials', async () => {
        localStorage.setItem('bgg_mock_cafe_snakes-and-lattes', JSON.stringify({
            cafe_id: 'snakes-and-lattes',
            name: 'Snakes & Lattes Annex',
            tagline: 'Toronto premier board game cafe with 1000+ titles.',
            bgg_username: 'snakesannex',
            wifi_ssid: 'Snakes-Guest',
            wifi_password: 'dicerollingfun',
            drink_pairings_enabled: true
        }));

        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/?cafe=snakes-and-lattes&table=8');

        window.CafePortal.parseVenueContext();
        await window.CafePortal.loadVenueMetadata();

        expect(document.getElementById('venue-name-title').textContent).toBe('Snakes & Lattes Annex');
        expect(document.getElementById('venue-tagline').textContent).toContain('Toronto premier board game cafe');
        expect(document.getElementById('header-table-badge').textContent).toBe('🪑 Table 8');
        expect(document.getElementById('wifi-ssid-label').textContent).toBe('Snakes-Guest');
        expect(document.getElementById('wifi-pass-label').textContent).toBe('(dicerollingfun)');
    });

    test('default view state is collection browser and switchTab toggles between views', () => {
        expect(window.CafePortal.state.activeTab).toBe('collection');

        // Switch to recommender
        window.CafePortal.switchTab('recommender');
        expect(window.CafePortal.state.activeTab).toBe('recommender');
        expect(document.getElementById('cafe-recommender-view').style.display).toBe('block');
        expect(document.getElementById('cafe-collection-view').style.display).toBe('none');
        expect(document.getElementById('tab-btn-recommender').classList.contains('active')).toBe(true);

        // Switch back to collection
        window.CafePortal.switchTab('collection');
        expect(window.CafePortal.state.activeTab).toBe('collection');
        expect(document.getElementById('cafe-collection-view').style.display).toBe('block');
        expect(document.getElementById('cafe-recommender-view').style.display).toBe('none');
        expect(document.getElementById('tab-btn-collection').classList.contains('active')).toBe(true);
    });

    test('loadCafeCollection fetches and renders library with shelf locations', async () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/?cafe=the-malt-and-meeple&table=4');

        window.CafePortal.parseVenueContext();
        await window.CafePortal.loadVenueMetadata();
        await window.CafePortal.loadCafeCollection();

        expect(window.CafePortal.state.collection.length).toBeGreaterThan(0);
        const grid = document.getElementById('cafe-collection-grid');
        expect(grid.children.length).toBeGreaterThan(0);

        // Verify games with shelf location have shelf badges
        const shelfBadges = grid.querySelectorAll('.shelf-location-badge');
        expect(shelfBadges.length).toBeGreaterThan(0);
        expect(shelfBadges[0].textContent).toContain('Shelf');
    });

    test('filterAndSortCollection filters games in real-time by search query and player chips', async () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/?cafe=the-malt-and-meeple&table=4');

        window.CafePortal.parseVenueContext();
        await window.CafePortal.loadVenueMetadata();
        await window.CafePortal.loadCafeCollection();

        // 1. Search for Cascadia
        window.CafePortal.state.searchQuery = 'Cascadia';
        window.CafePortal.filterAndSortCollection();
        expect(window.CafePortal.state.filteredCollection.length).toBe(1);
        expect(window.CafePortal.state.filteredCollection[0].name).toBe('Cascadia');

        // 2. Clear search and filter by 2p chip
        window.CafePortal.state.searchQuery = '';
        window.CafePortal.state.activeFilter = '2p';
        window.CafePortal.filterAndSortCollection();
        expect(window.CafePortal.state.filteredCollection.length).toBeGreaterThan(0);
        window.CafePortal.state.filteredCollection.forEach(g => {
            expect(g.min_players).toBeLessThanOrEqual(2);
            expect(g.max_players).toBeGreaterThanOrEqual(2);
        });

        // 3. Filter by shelved only
        window.CafePortal.state.activeFilter = 'shelved';
        window.CafePortal.filterAndSortCollection();
        window.CafePortal.state.filteredCollection.forEach(g => {
            expect(g.shelf_location).toBeTruthy();
        });
    });

    test('estimateTeachTime maps game complexity accurately', () => {
        expect(window.CafePortal.estimateTeachTime(1.2)).toBe('3-5 min teach');
        expect(window.CafePortal.estimateTeachTime(2.2)).toBe('5-10 min teach');
        expect(window.CafePortal.estimateTeachTime(3.0)).toBe('10-15 min teach');
        expect(window.CafePortal.estimateTeachTime(4.2)).toBe('15-20 min teach');
    });

    test('getDrinkPairing provides thematic suggestions for each vibe', () => {
        expect(window.CafePortal.getDrinkPairing('party')).toContain('Pilsner');
        expect(window.CafePortal.getDrinkPairing('deep_strategy')).toContain('Cold Brew');
        expect(window.CafePortal.getDrinkPairing('cooperative')).toContain('Shareable Craft Pitcher');
        expect(window.CafePortal.getDrinkPairing('direct_conflict')).toContain('Smoked Old Fashioned');
    });

    test('fetchCafeRecommendations retrieves mock cafe recommendations with shelf location and guru quotes', async () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/?cafe=the-malt-and-meeple&table=3');

        window.CafePortal.parseVenueContext();
        await window.CafePortal.loadVenueMetadata();

        window.CafePortal.state.quiz.playerCount = '4';
        window.CafePortal.state.quiz.duration = 'medium';
        window.CafePortal.state.quiz.vibe = 'casual_strategy';

        await window.CafePortal.fetchCafeRecommendations();

        const resultsContainer = document.getElementById('cafe-results-container');
        expect(resultsContainer.children.length).toBeGreaterThan(0);

        // Check for prominent shelf location badge
        const shelfBadges = resultsContainer.querySelectorAll('.shelf-location-badge');
        expect(shelfBadges.length).toBeGreaterThan(0);
        expect(shelfBadges[0].textContent).toContain('Shelf');

        // Check for teach time badge
        const teachBadges = resultsContainer.querySelectorAll('.teach-time-badge');
        expect(teachBadges.length).toBeGreaterThan(0);
        expect(teachBadges[0].textContent).toContain('teach');

        // Check for AI Sommelier quote
        const quotes = resultsContainer.querySelectorAll('.sommelier-quote-bubble');
        expect(quotes.length).toBeGreaterThan(0);
        expect(quotes[0].textContent).toContain('Cafe Guru Recommendation');

        // Check rules video button
        const videoBtn = resultsContainer.querySelector('.btn-card-action.primary');
        expect(videoBtn).not.toBeNull();
        expect(videoBtn.href).toContain('youtube.com');
    });

    test('fetchCafeRecommendations supports hobbyist group blend', async () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/?cafe=the-malt-and-meeple&table=2');

        window.CafePortal.parseVenueContext();
        await window.CafePortal.loadVenueMetadata();

        window.CafePortal.state.quiz.vibe = 'party';
        window.CafePortal.state.quiz.hobbyistUsers = 'gamer1,gamer2';

        await window.CafePortal.fetchCafeRecommendations();

        const resultsContainer = document.getElementById('cafe-results-container');
        expect(resultsContainer.children.length).toBeGreaterThan(0);
        expect(resultsContainer.textContent).toContain('Codenames');
    });

    test('renderCafeCards strictly does NOT render shelf location badge if game has no shelf_location', () => {
        const resultsContainer = document.getElementById('cafe-results-container');
        const recWithoutShelf = [
            {
                id: '999',
                name: 'Game Without Shelf',
                complexity: 2.0,
                rating: 7.5,
                reason: 'A great game with no physical shelf tag in comments.'
            }
        ];

        window.CafePortal.renderCafeCards(resultsContainer, recWithoutShelf);

        const shelfBadges = resultsContainer.querySelectorAll('.shelf-location-badge');
        expect(shelfBadges.length).toBe(0);
        expect(resultsContainer.textContent).not.toContain('📍');
        expect(resultsContainer.textContent).toContain('Game Without Shelf');
    });
});

