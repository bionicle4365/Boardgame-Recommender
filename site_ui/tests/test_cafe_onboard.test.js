import { describe, test, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

// Setup environment and load utils.js
const utilsJsPath = path.resolve(__dirname, '../assets/js/utils.js');
let rawCode = fs.readFileSync(utilsJsPath, 'utf8');

// Strip frontmatter and inject PLACEHOLDER_API_URL for mock mode
let code = rawCode.replace(/^---[\s\S]*?---/, '');
code = code.replace(/"\{\{\s*site\.cognito_client_id\s*\}\}"/g, '"mock-client-id"');
code = code.replace(/"\{\{\s*site\.cognito_region\s*\}\}"/g, '"us-east-1"');
code = code.replace(/"\{\{\s*site\.api_url\s*\}\}"/g, '"PLACEHOLDER_API_URL"');

eval(code);

describe('Cafe Onboarding Client Logic & Mock API', () => {
    function slugify(text) {
        return text.toString().toLowerCase().trim()
            .replace(/\s+/g, '-')
            .replace(/[^\w\-]+/g, '')
            .replace(/\-\-+/g, '-')
            .replace(/^-+/, '')
            .replace(/-+$/, '');
    }

    test('slugify converts venue names into URL-safe slugs', () => {
        expect(slugify("The Malt & Meeple Cafe!")).toBe("the-malt-meeple-cafe");
        expect(slugify("  Dice & Drinks (Downtown)  ")).toBe("dice-drinks-downtown");
        expect(slugify("Café & Games 2026")).toBe("caf-games-2026");
    });

    test('slug regex accepts valid slugs and rejects invalid formats', () => {
        const slugRegex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
        expect(slugRegex.test("malt-and-meeple")).toBe(true);
        expect(slugRegex.test("the-dice-box")).toBe(true);
        expect(slugRegex.test("cafe123")).toBe(true);

        expect(slugRegex.test("-leading-hyphen")).toBe(false);
        expect(slugRegex.test("trailing-hyphen-")).toBe(false);
        expect(slugRegex.test("double--hyphen")).toBe(false);
        expect(slugRegex.test("Upper-Case")).toBe(false);
        expect(slugRegex.test("spaces in slug")).toBe(false);
    });

    test('fetchApi mock handles /cafe/validate-bgg', async () => {
        const res = await window.fetchApi('/cafe/validate-bgg?username=maltandmeeple');
        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.status).toBe('success');
        expect(data.username).toBe('maltandmeeple');
        expect(data.total_owned).toBe(580);
        expect(data.shelf_tags_detected).toBe(412);
        expect(data.sample_matches.length).toBeGreaterThan(0);
        expect(data.sample_matches[0]).toHaveProperty('extracted_location');
    });

    test('fetchApi mock handles /cafe/check-slug', async () => {
        const availRes = await window.fetchApi('/cafe/check-slug?slug=unique-new-cafe');
        const availData = await availRes.json();
        expect(availData.available).toBe(true);

        const takenRes = await window.fetchApi('/cafe/check-slug?slug=the-dice-box-official');
        const takenData = await takenRes.json();
        expect(takenData.available).toBe(false);
    });

    test('fetchApi mock handles /cafe/onboard registration', async () => {
        const payload = {
            cafe_id: 'test-boardgame-lounge',
            name: 'Test Board Game Lounge',
            bgg_username: 'testcafe',
            table_count: 24,
            wifi_ssid: 'LoungeGuest',
            wifi_password: 'rolltwenty',
            drink_pairings_enabled: true
        };

        const res = await window.fetchApi('/cafe/onboard', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.status).toBe('success');
        expect(data.cafe.cafe_id).toBe('test-boardgame-lounge');
        expect(data.cafe.table_count).toBe(24);
    });

    test('fetchApi mock handles /cafe/meta retrieval', async () => {
        const res = await window.fetchApi('/cafe/meta?cafe_id=test-boardgame-lounge');
        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data).toHaveProperty('name');
        expect(data).toHaveProperty('table_count');
    });

    test('fetchApi mock handles /cafe/sync on-demand sync trigger', async () => {
        const res = await window.fetchApi('/cafe/sync', {
            method: 'POST',
            body: JSON.stringify({ cafe_id: 'test-boardgame-lounge' })
        });
        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.status).toBe('success');
        expect(data.cafe_id).toBe('test-boardgame-lounge');
        expect(data).toHaveProperty('last_sync_timestamp');
    });
});
