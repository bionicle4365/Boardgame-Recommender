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
            <!-- Video Modal -->
            <div class="cafe-video-modal-overlay" id="rules-video-modal" style="display: none;">
                <h3 id="modal-game-title"></h3>
                <button id="btn-close-video-modal">✕</button>
                <div id="video-player-container">
                    <iframe id="rules-video-iframe" src=""></iframe>
                </div>
                <div id="video-fallback-notice" style="display: none;">
                    <a id="video-external-search-link" href="#"></a>
                </div>
                <span id="modal-teach-time"></span>
                <span id="modal-complexity"></span>
                <a id="modal-bgg-link" href="#"></a>
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
        const videoBtn = resultsContainer.querySelector('.btn-watch-rules');
        expect(videoBtn).not.toBeNull();
        expect(videoBtn.textContent).toContain('Watch Rules');
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

    test('loadCafeCollection falls back to /recommendations when /cafe/collection throws or fails', async () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/?cafe=the-malt-and-meeple&table=4');

        window.CafePortal.parseVenueContext();
        await window.CafePortal.loadVenueMetadata();

        const originalFetchApi = window.fetchApi;
        window.fetchApi = vi.fn(async (endpoint, options) => {
            if (endpoint.startsWith('/cafe/collection')) {
                throw new TypeError('Failed to fetch due to CORS / network error');
            }
            return originalFetchApi(endpoint, options);
        });

        try {
            await window.CafePortal.loadCafeCollection();
            expect(window.CafePortal.state.collection.length).toBeGreaterThan(0);
            const grid = document.getElementById('cafe-collection-grid');
            expect(grid.children.length).toBeGreaterThan(0);
        } finally {
            window.fetchApi = originalFetchApi;
        }
    });

    test('extractYouTubeId extracts valid 11-char video IDs from various URL formats', () => {
        expect(window.CafePortal.extractYouTubeId('https://www.youtube.com/watch?v=zQVHkl8oQEU')).toBe('zQVHkl8oQEU');
        expect(window.CafePortal.extractYouTubeId('https://youtu.be/lgDgcLI2B0U')).toBe('lgDgcLI2B0U');
        expect(window.CafePortal.extractYouTubeId('https://www.youtube.com/embed/yflGY5bW_1g')).toBe('yflGY5bW_1g');
        expect(window.CafePortal.extractYouTubeId('https://vimeo.com/123456')).toBeNull();
        expect(window.CafePortal.extractYouTubeId(null)).toBeNull();
    });

    test('openRulesVideoModal populates video modal and sets YouTube embed iframe', () => {
        const game = {
            id: '266192',
            name: 'Wingspan',
            complexity: 2.4,
            teach_time: '10 min teach',
            rules_video_url: 'https://www.youtube.com/watch?v=lgDgcLI2B0U',
            rules_video_id: 'lgDgcLI2B0U'
        };

        window.CafePortal.openRulesVideoModal(game);

        const modal = document.getElementById('rules-video-modal');
        const title = document.getElementById('modal-game-title');
        const iframe = document.getElementById('rules-video-iframe');
        const teachTime = document.getElementById('modal-teach-time');
        const complexity = document.getElementById('modal-complexity');
        const videoContainer = document.getElementById('video-player-container');
        const fallbackNotice = document.getElementById('video-fallback-notice');

        expect(modal.style.display).toBe('flex');
        expect(title.textContent).toBe('Wingspan');
        expect(teachTime.textContent).toContain('10 min teach');
        expect(complexity.textContent).toContain('2.4 / 5');
        expect(videoContainer.style.display).toBe('block');
        expect(fallbackNotice.style.display).toBe('none');
        expect(iframe.src).toContain('https://www.youtube-nocookie.com/embed/lgDgcLI2B0U');
    });

    test('openRulesVideoModal shows fallback YouTube search when game has no video', () => {
        const game = {
            id: '999',
            name: 'Mystery Game',
            complexity: 1.5,
            teach_time: '3 min teach',
            rules_video_url: null,
            rules_video_id: null
        };

        window.CafePortal.openRulesVideoModal(game);

        const modal = document.getElementById('rules-video-modal');
        const videoContainer = document.getElementById('video-player-container');
        const fallbackNotice = document.getElementById('video-fallback-notice');
        const searchLink = document.getElementById('video-external-search-link');

        expect(modal.style.display).toBe('flex');
        expect(videoContainer.style.display).toBe('none');
        expect(fallbackNotice.style.display).toBe('block');
        expect(searchLink.href).toContain('youtube.com/results?search_query=');
        expect(searchLink.href).toContain('Mystery%20Game');
    });

    test('closeRulesVideoModal hides modal and clears iframe src to stop playback', () => {
        const game = {
            id: '178900',
            name: 'Codenames',
            rules_video_url: 'https://www.youtube.com/watch?v=zQVHkl8oQEU'
        };

        window.CafePortal.openRulesVideoModal(game);
        const modal = document.getElementById('rules-video-modal');
        const iframe = document.getElementById('rules-video-iframe');

        expect(modal.style.display).toBe('flex');
        expect(iframe.src).toContain('zQVHkl8oQEU');

        window.CafePortal.closeRulesVideoModal();

        expect(modal.style.display).toBe('none');
        expect(iframe.src).not.toContain('zQVHkl8oQEU');
        expect(iframe.getAttribute('src')).toBeFalsy();
    });

    test('renderCafeCards attaches Watch Rules buttons that trigger video modal', () => {
        const grid = document.getElementById('cafe-collection-grid');
        const games = [
            {
                id: '230802',
                name: 'Azul',
                complexity: 1.8,
                teach_time: '5 min teach',
                rules_video_url: 'https://www.youtube.com/watch?v=yflGY5bW_1g'
            }
        ];

        window.CafePortal.state.collection = games;
        window.CafePortal.renderCafeCards(grid, games);
        window.CafePortal.setupVideoModalControls();

        const watchBtn = grid.querySelector('.btn-watch-rules');
        expect(watchBtn).not.toBeNull();
        expect(watchBtn.getAttribute('data-game-id')).toBe('230802');

        watchBtn.click();

        const modal = document.getElementById('rules-video-modal');
        const title = document.getElementById('modal-game-title');
        const iframe = document.getElementById('rules-video-iframe');

        expect(modal.style.display).toBe('flex');
        expect(title.textContent).toBe('Azul');
        expect(iframe.src).toContain('yflGY5bW_1g');
    });
});


