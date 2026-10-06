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
            <div id="vibe-quiz-form"></div>
            <div id="venue-name-title"></div>
            <div id="venue-tagline"></div>
            <div id="header-table-badge"></div>
            <div id="header-wifi-chip" style="display: none;">
                <span id="wifi-ssid-label"></span>
                <span id="wifi-pass-label"></span>
            </div>
            <div id="results-section" style="display: none;">
                <span id="results-table-num"></span>
                <div id="cafe-results-container"></div>
            </div>
            <button id="quiz-submit-btn"></button>
        `;
    });

    test('parseVenueContext extracts cafe and table from URL search params', () => {
        // Set mock window.location
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

        window.CafePortal.parseVenueContext();
        expect(window.CafePortal.state.cafeId).toBe('the-dice-box-cafe');
        expect(window.CafePortal.state.table).toBe('12');
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
});
