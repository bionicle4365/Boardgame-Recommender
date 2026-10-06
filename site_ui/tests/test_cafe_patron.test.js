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

// Load AnnouncementBanner script from include
const bannerHtmlPath = path.resolve(__dirname, '../_includes/announcement_banner.html');
const rawBannerHtml = fs.readFileSync(bannerHtmlPath, 'utf8');
const bannerScriptMatch = rawBannerHtml.match(/<script>([\s\S]*?)<\/script>/);
if (bannerScriptMatch) {
    eval(bannerScriptMatch[1]);
}

describe('Cafe Patron Portal & Vibe Check Client Logic', () => {
    beforeEach(() => {
        localStorage.clear();
        sessionStorage.clear();
        document.body.innerHTML = `
            <!-- Global Announcement Banner (Reusable Include) -->
            <div id="site-announcement-banner" class="site-announcement-banner banner-info" style="display: none;" data-banner-id="site-global-announcement">
                <span id="announcement-banner-icon">📢</span>
                <span id="announcement-banner-text"></span>
                <a id="announcement-banner-cta" href="#" style="display: none;"><span id="announcement-banner-cta-text">Learn More →</span></a>
                <button id="announcement-banner-dismiss">✕</button>
            </div>
            <div id="cafe-patron-view">
                <div id="vibe-quiz-form"></div>
                <div id="venue-name-title"></div>
                <div id="venue-tagline"></div>
                <div id="header-table-badge"></div>
                <a id="header-menu-btn" class="header-menu-cta-btn" href="#" target="_blank" style="display: none;">🍺 Food &amp; Drinks Menu ↗</a>
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
                    <!-- Guru Picks Spotlight Carousel (Milestone C10) -->
                    <div id="cafe-guru-picks-section" style="display: none;">
                        <span id="guru-picks-count-badge"></span>
                        <div id="guru-picks-carousel"></div>
                    </div>
                    <button id="btn-launch-recommender"></button>
                    <input id="cafe-search-input">
                    <button id="cafe-search-clear" style="display: none;"></button>
                    <div id="collection-quick-filters">
                        <button class="cafe-filter-chip active" data-filter="all"></button>
                        <button class="cafe-filter-chip" data-filter="small_table"></button>
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
            <!-- Table Voting Modal (Milestone C7) -->
            <button id="btn-start-table-vote" style="display: none;"></button>
            <div class="table-vote-cta-card" id="table-vote-cta-card">
                <button id="btn-launch-table-vote"></button>
            </div>
            <button id="btn-banner-start-poll"></button>
            <div id="cafe-table-vote-modal" style="display: none;">
                <h3 id="vote-modal-title"></h3>
                <button id="btn-close-vote-modal">✕</button>
                <div id="vote-setup-section">
                    <input id="poll-search-input">
                    <button id="poll-search-clear" style="display: none;"></button>
                    <button id="btn-poll-select-rec"></button>
                    <button id="btn-poll-clear-all"></button>
                    <span id="poll-selected-count-chip">0 selected</span>
                    <div id="poll-candidates-picker"></div>
                    <div id="poll-setup-error" style="display: none;"></div>
                    <button id="btn-launch-configured-poll"></button>
                </div>
                <div id="vote-active-section" style="display: none;">
                    <img id="vote-modal-qr-img" src="">
                    <button id="btn-vote-copy-link"></button>
                    <button id="btn-vote-share-link"></button>
                    <a id="btn-vote-open-external" href="#"></a>
                    <div id="vote-copy-feedback" style="display: none;"></div>
                    <div id="vote-ballot-section">
                        <input id="vote-voter-name-input">
                        <div id="vote-candidates-list"></div>
                        <button id="btn-submit-table-vote"></button>
                    </div>
                    <div id="vote-consensus-section" style="display: none;">
                        <div id="vote-winner-banner" style="display: none;">
                            <h4 id="vote-winner-title"></h4>
                        </div>
                        <span id="vote-tally-count"></span>
                        <div id="vote-rankings-list"></div>
                        <button id="btn-revote-trigger"></button>
                        <button id="btn-refresh-tally"></button>
                    </div>
                </div>
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

    test('parseVenueContext extracts cafe and table from RESTful path /cafe/:slug/:table', () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/pawtucket-library/1');

        const hasVenue = window.CafePortal.parseVenueContext();
        expect(hasVenue).toBe(true);
        expect(window.CafePortal.state.cafeId).toBe('pawtucket-library');
        expect(window.CafePortal.state.table).toBe('1');
        expect(sessionStorage.getItem('cafe_patron_cafe_id')).toBe('pawtucket-library');
        expect(sessionStorage.getItem('cafe_patron_table')).toBe('1');
    });

    test('parseVenueContext extracts cafe and table from /cafe/:slug/table/:table', () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/maltandmeeple/table/7');

        const hasVenue = window.CafePortal.parseVenueContext();
        expect(hasVenue).toBe(true);
        expect(window.CafePortal.state.cafeId).toBe('maltandmeeple');
        expect(window.CafePortal.state.table).toBe('7');
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

    test('venue-header-card is structured as a div to avoid header tag collisions and toolbar is sticky', () => {
        const cafeHtmlPath = path.resolve(__dirname, '../cafe/index.html');
        const cafeHtml = fs.readFileSync(cafeHtmlPath, 'utf8');

        // Venue header card must not use <header> element
        expect(cafeHtml).toMatch(/<div class="venue-header-card"/);
        expect(cafeHtml).not.toMatch(/<header class="venue-header-card"/);

        // Cafe CSS must configure collection-browser-toolbar as sticky
        const cafeCssPath = path.resolve(__dirname, '../assets/css/cafe.css');
        const cafeCss = fs.readFileSync(cafeCssPath, 'utf8');

        expect(cafeCss).toContain('.collection-browser-toolbar {');
        expect(cafeCss).toMatch(/\.collection-browser-toolbar\s*\{[^}]*position:\s*sticky;/s);
        expect(cafeCss).toMatch(/\.collection-browser-toolbar\s*\{[^}]*top:\s*70px;/s);
        expect(cafeCss).toMatch(/\.venue-header-card\s*\{[^}]*z-index:\s*1;/s);
    });

    test('startTableVote creates table vote session via API and populates modal with QR code', async () => {
        const games = [
            { id: '13', name: 'Catan', complexity: 2.3, thumbnail: 'https://example.com/catan.jpg', shelf_location: 'A-1' },
            { id: '266192', name: 'Wingspan', complexity: 2.4, thumbnail: 'https://example.com/wingspan.jpg', shelf_location: 'B-2' },
            { id: '174430', name: 'Gloomhaven', complexity: 3.8, thumbnail: 'https://example.com/gloom.jpg', shelf_location: 'C-3' }
        ];

        window.CafePortal.state.recommendations = games;
        window.CafePortal.state.cafeId = 'the-malt-and-meeple';
        window.CafePortal.state.table = '5';
        window.CafePortal.state.venueMeta = { name: 'The Malt & Meeple' };

        let apiCalledWith = null;
        window.fetchApi = async (url, options) => {
            apiCalledWith = { url, options: JSON.parse(options.body) };
            return {
                ok: true,
                json: async () => ({
                    session_id: 'test_sess_123',
                    group_name: 'The Malt & Meeple - Table 5',
                    table_number: '5',
                    candidates: games
                })
            };
        };

        await window.CafePortal.startTableVote();

        expect(apiCalledWith.url).toBe('/cafe/vote/start');
        expect(apiCalledWith.options.table).toBe('5');
        expect(apiCalledWith.options.candidates.length).toBe(3);
        expect(apiCalledWith.options.duration_hours).toBe(0.25);

        const modal = document.getElementById('cafe-table-vote-modal');
        const modalTitle = document.getElementById('vote-modal-title');
        const qrImg = document.getElementById('vote-modal-qr-img');
        const candidatesList = document.getElementById('vote-candidates-list');

        expect(modal.style.display).toBe('flex');
        expect(modalTitle.textContent).toContain('The Malt & Meeple - Table 5 Vote');
        expect(qrImg.src).toContain('test_sess_123');
        expect(candidatesList.children.length).toBe(3);
    });

    test('submitTableVoteBallot submits votes and renders consensus standings', async () => {
        const games = [
            { id: '13', name: 'Catan', complexity: 2.3 },
            { id: '266192', name: 'Wingspan', complexity: 2.4 }
        ];

        window.CafePortal.state.activeVoteSession = {
            session_id: 'sess_vote_abc',
            candidates: games
        };
        window.CafePortal.state.userBallot = { '13': 'yes', '266192': 'neutral' };
        window.CafePortal.state.table = '2';

        let votePayload = null;
        window.fetchApi = async (url, options) => {
            votePayload = JSON.parse(options.body);
            return {
                ok: true,
                json: async () => ({
                    session_id: 'sess_vote_abc',
                    consensus: {
                        total_voters: 1,
                        winner: games[0],
                        rankings: [
                            { candidate: games[0], score: 2, is_vetoed: false },
                            { candidate: games[1], score: 1, is_vetoed: false }
                        ]
                    }
                })
            };
        };

        await window.CafePortal.submitTableVoteBallot();

        expect(votePayload.session_id).toBe('sess_vote_abc');
        expect(votePayload.votes['13']).toBe('yes');

        const consensusSection = document.getElementById('vote-consensus-section');
        const winnerBanner = document.getElementById('vote-winner-banner');
        const winnerTitle = document.getElementById('vote-winner-title');
        const tallyCount = document.getElementById('vote-tally-count');

        expect(consensusSection.style.display).toBe('flex');
        expect(winnerBanner.style.display).toBe('flex');
        expect(winnerTitle.textContent).toBe('Catan');
        expect(tallyCount.textContent).toBe('1');
    });

    test('setupTableVotingControls wires close button and revote triggers', () => {
        window.CafePortal.setupTableVotingControls();

        const modal = document.getElementById('cafe-table-vote-modal');
        const closeBtn = document.getElementById('btn-close-vote-modal');
        const ballotSection = document.getElementById('vote-ballot-section');
        const consensusSection = document.getElementById('vote-consensus-section');
        const revoteBtn = document.getElementById('btn-revote-trigger');

        modal.style.display = 'flex';
        closeBtn.click();
        expect(modal.style.display).toBe('none');

        ballotSection.style.display = 'none';
        consensusSection.style.display = 'flex';
        revoteBtn.click();
        expect(ballotSection.style.display).toBe('flex');
        expect(consensusSection.style.display).toBe('none');
    });

    test('updateTableVoteUI displays Vote with Table button and hides Start Table Vote card when vote is active', () => {
        const startBtn = document.getElementById('btn-start-table-vote');
        const ctaCard = document.getElementById('table-vote-cta-card');

        // Initially no active vote
        window.CafePortal.state.activeVoteSession = null;
        window.CafePortal.updateTableVoteUI();
        expect(startBtn.style.display).toBe('none');
        expect(ctaCard.style.display).toBe('flex');

        // With active vote session within 15 mins TTL
        const future = new Date(Date.now() + 15 * 60 * 1000).toISOString();
        window.CafePortal.state.activeVoteSession = {
            session_id: 'active_123',
            closes_at: future,
            is_closed: false,
            candidates: [{ id: '13', name: 'Catan' }]
        };
        window.CafePortal.updateTableVoteUI();
        expect(startBtn.style.display).toBe('inline-flex');
        expect(ctaCard.style.display).toBe('none');

        // When session expired
        const past = new Date(Date.now() - 1000).toISOString();
        window.CafePortal.state.activeVoteSession = {
            session_id: 'expired_123',
            closes_at: past,
            is_closed: false
        };
        window.CafePortal.updateTableVoteUI();
        expect(startBtn.style.display).toBe('none');
        expect(ctaCard.style.display).toBe('flex');
    });

    test('clicking Vote with Table button opens active vote modal instead of starting a new vote', () => {
        const startBtn = document.getElementById('btn-start-table-vote');
        const modal = document.getElementById('cafe-table-vote-modal');
        const future = new Date(Date.now() + 15 * 60 * 1000).toISOString();

        window.CafePortal.state.activeVoteSession = {
            session_id: 'active_123',
            closes_at: future,
            is_closed: false,
            candidates: [{ id: '13', name: 'Catan' }]
        };

        window.CafePortal.setupTableVotingControls();
        modal.style.display = 'none';

        startBtn.click();
        expect(modal.style.display).toBe('flex');
    });

    test('base cafe URL hides table-badge-pill and leaves state.table empty', async () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/pawtucket-library');

        const hasVenue = window.CafePortal.parseVenueContext();
        expect(hasVenue).toBe(true);
        expect(window.CafePortal.state.cafeId).toBe('pawtucket-library');
        expect(window.CafePortal.state.table).toBe('');

        await window.CafePortal.loadVenueMetadata();
        const badge = document.getElementById('header-table-badge');
        expect(badge.style.display).toBe('none');
    });

    test('table badge pill displays custom room name when specified', async () => {
        delete window.location;
        window.location = new URL('https://meeplemanifesto.com/cafe/pawtucket-library/The%20Vault');

        window.CafePortal.parseVenueContext();
        expect(window.CafePortal.state.table).toBe('The Vault');

        await window.CafePortal.loadVenueMetadata();
        const badge = document.getElementById('header-table-badge');
        expect(badge.style.display).toBe('inline-flex');
        expect(badge.textContent).toBe('🪑 The Vault');
    });

    test('openPollCreationModal shows all cafe games with recommended pre-selected at top and text search filtering', async () => {
        const fullLibrary = [
            { id: '101', name: '7 Wonders', rating: 7.7, complexity: 2.3, playing_time: 30, mechanics: ['Card Drafting'] },
            { id: '102', name: 'Azul', rating: 7.8, complexity: 1.8, playing_time: 45, mechanics: ['Tile Placement'] },
            { id: '103', name: 'Brass Birmingham', rating: 8.6, complexity: 3.9, playing_time: 120, mechanics: ['Economic', 'Network'] },
            { id: '104', name: 'Catan', rating: 7.1, complexity: 2.3, playing_time: 75, mechanics: ['Trading'] }
        ];

        window.CafePortal.state.collection = fullLibrary;
        window.CafePortal.state.recommendations = [fullLibrary[1], fullLibrary[2]]; // Azul and Brass
        window.CafePortal.state.cafeId = 'demo-cafe';
        window.CafePortal.state.table = '3';

        await window.CafePortal.openPollCreationModal();

        const setupSection = document.getElementById('vote-setup-section');
        const activeSection = document.getElementById('vote-active-section');
        const picker = document.getElementById('poll-candidates-picker');
        const countChip = document.getElementById('poll-selected-count-chip');

        expect(setupSection.style.display).toBe('flex');
        expect(activeSection.style.display).toBe('none');
        expect(countChip.textContent).toBe('2 selected');

        // Check that all 4 games are in the picker
        const items = picker.querySelectorAll('.poll-candidate-item');
        expect(items.length).toBe(4);

        // First items in list should be the selected/recommended games (Azul, Brass)
        const firstId = items[0].getAttribute('data-game-id');
        const secondId = items[1].getAttribute('data-game-id');
        expect(['102', '103']).toContain(firstId);
        expect(['102', '103']).toContain(secondId);

        // Real-time search filter
        window.CafePortal.state.pollSearchQuery = 'catan';
        window.CafePortal.renderPollCandidatePicker();
        const filteredItems = picker.querySelectorAll('.poll-candidate-item');
        expect(filteredItems.length).toBe(1);
        expect(filteredItems[0].querySelector('.poll-cand-title').textContent).toBe('Catan');

        // Clear search
        window.CafePortal.state.pollSearchQuery = '';
        window.CafePortal.renderPollCandidatePicker();
        expect(picker.querySelectorAll('.poll-candidate-item').length).toBe(4);
    });

    // ── Milestone C10 Venue Hospitality & Table Experience Tests ────────────

    test('AnnouncementBanner module displays announcement, handles dismissal, and respects localStorage state', () => {
        expect(window.AnnouncementBanner).toBeDefined();

        const shown = window.AnnouncementBanner.show({
            id: 'test-event-banner-1',
            text: '🎉 Trivia Night tonight at 7:30 PM! $5 pints',
            link: 'https://example.com/trivia',
            linkText: 'RSVP Now →',
            type: 'event',
            icon: '🎉',
            dismissible: true
        });

        expect(shown).toBe(true);
        const banner = document.getElementById('site-announcement-banner');
        const text = document.getElementById('announcement-banner-text');
        const cta = document.getElementById('announcement-banner-cta');
        const icon = document.getElementById('announcement-banner-icon');

        expect(banner.style.display).toBe('block');
        expect(banner.classList.contains('banner-event')).toBe(true);
        expect(text.textContent).toBe('🎉 Trivia Night tonight at 7:30 PM! $5 pints');
        expect(cta.href).toBe('https://example.com/trivia');
        expect(cta.style.display).toBe('inline-flex');
        expect(icon.textContent).toBe('🎉');

        // Dismiss the banner
        window.AnnouncementBanner.dismiss('test-event-banner-1');
        expect(window.AnnouncementBanner.isDismissed('test-event-banner-1')).toBe(true);

        // Attempting to show again should return false and not display
        const shownAgain = window.AnnouncementBanner.show({
            id: 'test-event-banner-1',
            text: '🎉 Trivia Night tonight at 7:30 PM! $5 pints'
        });
        expect(shownAgain).toBe(false);

        // Reset dismissal
        window.AnnouncementBanner.reset('test-event-banner-1');
        expect(window.AnnouncementBanner.isDismissed('test-event-banner-1')).toBe(false);
    });

    test('loadVenueMetadata populates Food & Drinks Menu CTA button when menu_url is configured', async () => {
        window.CafePortal.state.cafeId = 'the-malt-and-meeple';
        const originalFetchApi = window.fetchApi;

        window.fetchApi = async (url) => {
            if (url.includes('/cafe/meta')) {
                return {
                    ok: true,
                    json: async () => ({
                        cafe_id: 'the-malt-and-meeple',
                        name: 'The Malt & Meeple',
                        menu_url: 'https://toasttab.com/malt-and-meeple/menu',
                        announcement_banner: '🍺 Half-price drafts till 7PM!'
                    })
                };
            }
            return originalFetchApi(url);
        };

        try {
            await window.CafePortal.loadVenueMetadata();

            const menuBtn = document.getElementById('header-menu-btn');
            expect(menuBtn).not.toBeNull();
            expect(menuBtn.style.display).toBe('inline-flex');
            expect(menuBtn.href).toBe('https://toasttab.com/malt-and-meeple/menu');

            // Banner should also be displayed
            const banner = document.getElementById('site-announcement-banner');
            expect(banner.style.display).toBe('block');
            const text = document.getElementById('announcement-banner-text');
            expect(text.textContent).toContain('Half-price drafts');
        } finally {
            window.fetchApi = originalFetchApi;
        }
    });

    test('renderGuruPicks renders spotlight carousel cards for venue featured_game_ids', () => {
        const library = [
            { id: '13', name: 'Catan', rating: 7.1, complexity: 2.3, playing_time: 75, shelf_location: 'A-1' },
            { id: '266192', name: 'Wingspan', rating: 8.1, complexity: 2.4, playing_time: 70, shelf_location: 'B-2' },
            { id: '178900', name: 'Codenames', rating: 7.6, complexity: 1.3, playing_time: 15, shelf_location: 'C-3' },
            { id: '999', name: 'Unfeatured Game', rating: 6.0, complexity: 2.0, playing_time: 30 }
        ];

        window.CafePortal.state.collection = library;
        window.CafePortal.state.venueMeta = {
            featured_game_ids: ['13', '266192', '178900']
        };

        window.CafePortal.renderGuruPicks();

        const section = document.getElementById('cafe-guru-picks-section');
        const carousel = document.getElementById('guru-picks-carousel');
        const countBadge = document.getElementById('guru-picks-count-badge');

        expect(section.style.display).toBe('block');
        expect(countBadge.textContent).toBe('3 Featured');

        const cards = carousel.querySelectorAll('.guru-pick-card');
        expect(cards.length).toBe(3);

        const cardNames = Array.from(cards).map(c => c.querySelector('.guru-pick-name').textContent);
        expect(cardNames).toContain('Catan');
        expect(cardNames).toContain('Wingspan');
        expect(cardNames).toContain('Codenames');
        expect(cardNames).not.toContain('Unfeatured Game');

        // Verify badge and watch rules button
        expect(cards[0].querySelector('.guru-pick-badge').textContent).toBe('⭐ House Pick');
        expect(cards[0].querySelector('.btn-watch-rules')).not.toBeNull();
    });

    test('isSmallTableFriendly accurately identifies compact games and filters library', () => {
        const compactGame1 = { id: '1', name: 'Love Letter', categories: ['Card Game', 'Deduction'], playing_time: 20, complexity: 1.2 };
        const compactGame2 = { id: '2', name: 'Hive', categories: ['Abstract Strategy'], playing_time: 20, complexity: 2.3 };
        const compactGame3 = { id: '3', name: 'Sea Salt & Paper', categories: ['Card Game'], playing_time: 30, complexity: 1.8 };
        const compactGame4 = { id: '4', name: 'Sushi Go!', categories: ['Card Game'], playing_time: 15, complexity: 1.1 };
        const sprawlingGame1 = { id: '5', name: 'Scythe', categories: ['Economic', 'Miniatures'], playing_time: 115, complexity: 3.4 };
        const sprawlingGame2 = { id: '6', name: 'Gloomhaven', categories: ['Adventure', 'Miniatures'], playing_time: 120, complexity: 3.8 };

        expect(window.CafePortal.isSmallTableFriendly(compactGame1)).toBe(true);
        expect(window.CafePortal.isSmallTableFriendly(compactGame2)).toBe(true);
        expect(window.CafePortal.isSmallTableFriendly(compactGame3)).toBe(true);
        expect(window.CafePortal.isSmallTableFriendly(compactGame4)).toBe(true);
        expect(window.CafePortal.isSmallTableFriendly(sprawlingGame1)).toBe(false);
        expect(window.CafePortal.isSmallTableFriendly(sprawlingGame2)).toBe(false);

        // Test filtering via filterAndSortCollection
        const library = [compactGame1, compactGame2, sprawlingGame1, sprawlingGame2];
        window.CafePortal.state.collection = library;
        window.CafePortal.state.searchQuery = '';
        window.CafePortal.state.activeFilter = 'small_table';

        window.CafePortal.filterAndSortCollection();

        expect(window.CafePortal.state.filteredCollection.length).toBe(2);
        const filteredIds = window.CafePortal.state.filteredCollection.map(g => g.id);
        expect(filteredIds).toEqual(['2', '1']);
    });
});


