import { describe, test, expect, beforeEach } from 'vitest';
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

describe('Cafe Management Client Logic & Mock API', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    test('fetchApi mock handles /cafe/my-cafes returning default demo cafe when empty', async () => {
        const res = await window.fetchApi('/cafe/my-cafes');
        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.status).toBe('success');
        expect(Array.isArray(data.cafes)).toBe(true);
        expect(data.cafes.length).toBeGreaterThan(0);
        expect(data.cafes[0].cafe_id).toBe('the-malt-and-meeple');
        expect(data.cafes[0].name).toBe('The Malt & Meeple Cafe');
        expect(data.cafes[0].table_count).toBe(20);
    });

    test('fetchApi mock handles /cafe/my-cafes returning multiple registered cafes', async () => {
        localStorage.setItem('bgg_mock_cafe_venue-alpha', JSON.stringify({
            cafe_id: 'venue-alpha',
            name: 'Alpha Cafe',
            table_count: 12
        }));
        localStorage.setItem('bgg_mock_cafe_venue-beta', JSON.stringify({
            cafe_id: 'venue-beta',
            name: 'Beta Lounge',
            table_count: 18
        }));

        const res = await window.fetchApi('/cafe/my-cafes');
        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.status).toBe('success');
        expect(data.cafes.length).toBe(2);
        const ids = data.cafes.map(c => c.cafe_id);
        expect(ids).toContain('venue-alpha');
        expect(ids).toContain('venue-beta');
    });

    test('fetchApi mock handles /cafe/update modifying venue settings', async () => {
        localStorage.setItem('bgg_mock_cafe_the-malt-and-meeple', JSON.stringify({
            cafe_id: 'the-malt-and-meeple',
            name: 'Old Name',
            table_count: 10,
            wifi_ssid: 'OldSSID',
            staff_pin: '1234'
        }));

        const updatePayload = {
            cafe_id: 'the-malt-and-meeple',
            name: 'The Malt & Meeple Gastropub',
            table_count: 35,
            wifi_ssid: 'MaltMeeple-Guest',
            wifi_password: 'rollinitiative',
            tagline: 'Craft beer and board games'
        };

        const res = await window.fetchApi('/cafe/update', {
            method: 'POST',
            body: JSON.stringify(updatePayload)
        });

        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.status).toBe('success');
        expect(data.cafe.name).toBe('The Malt & Meeple Gastropub');
        expect(data.cafe.table_count).toBe(35);
        expect(data.cafe.wifi_ssid).toBe('MaltMeeple-Guest');
        expect(data.cafe).not.toHaveProperty('staff_pin');

        // Verify saved in localStorage
        const stored = JSON.parse(localStorage.getItem('bgg_mock_cafe_the-malt-and-meeple'));
        expect(stored.name).toBe('The Malt & Meeple Gastropub');
        expect(stored.table_count).toBe(35);
    });

    test('validates table count numeric range bounds', () => {
        function validateTableCount(val) {
            const num = parseInt(val, 10);
            if (isNaN(num) || num < 1 || num > 500) return false;
            return true;
        }

        expect(validateTableCount("20")).toBe(true);
        expect(validateTableCount(1)).toBe(true);
        expect(validateTableCount(500)).toBe(true);
        expect(validateTableCount(0)).toBe(false);
        expect(validateTableCount(-5)).toBe(false);
        expect(validateTableCount(501)).toBe(false);
        expect(validateTableCount("abc")).toBe(false);
    });

    test('settings page contains single register button in header and none at bottom of list', () => {
        const settingsHtml = fs.readFileSync(path.resolve(__dirname, '../settings/index.html'), 'utf8');
        expect(settingsHtml).toContain('id="settings-register-cafe-top-btn"');
        expect(settingsHtml).not.toContain('Register Another Venue');
    });

    test('fetchApi mock handles /cafe/delete removing venue from storage', async () => {
        localStorage.setItem('bgg_mock_cafe_to-delete', JSON.stringify({
            cafe_id: 'to-delete',
            name: 'Doomed Cafe',
            table_count: 5
        }));

        const res = await window.fetchApi('/cafe/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cafe_id: 'to-delete' })
        });
        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.status).toBe('success');
        expect(data.message).toContain('deleted successfully');
        expect(localStorage.getItem('bgg_mock_cafe_to-delete')).toBeNull();
    });

    test('manage.html contains Danger Zone and Delete Cafe confirmation modal', () => {
        const manageHtml = fs.readFileSync(path.resolve(__dirname, '../cafe/manage.html'), 'utf8');
        expect(manageHtml).toContain('id="open-delete-cafe-modal-btn"');
        expect(manageHtml).toContain('id="delete-cafe-modal"');
        expect(manageHtml).toContain('id="confirm-delete-cafe-btn"');
        expect(manageHtml).toContain('id="cancel-delete-cafe-btn"');
        expect(manageHtml).toContain('Danger Zone');
    });

    test('manage.html contains custom room names input field and handles room names in mock update', async () => {
        const manageHtml = fs.readFileSync(path.resolve(__dirname, '../cafe/manage.html'), 'utf8');
        expect(manageHtml).toContain('id="manage-room-names-input"');
        expect(manageHtml).toContain('Custom Room / Table Names');

        const updatePayload = {
            cafe_id: 'the-malt-and-meeple',
            name: 'The Malt & Meeple',
            table_count: 20,
            room_names: ['The Vault', "Dragon's Lair"]
        };

        const res = await window.fetchApi('/cafe/update', {
            method: 'POST',
            body: JSON.stringify(updatePayload)
        });

        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.cafe.room_names).toEqual(['The Vault', "Dragon's Lair"]);
    });

    test('manage.html contains C10 hospitality fields for menu, announcement banner, and featured games', () => {
        const manageHtml = fs.readFileSync(path.resolve(__dirname, '../cafe/manage.html'), 'utf8');
        expect(manageHtml).toContain('id="manage-menu-url-input"');
        expect(manageHtml).toContain('id="manage-announcement-input"');
        expect(manageHtml).toContain('id="manage-featured-games-input"');
        expect(manageHtml).toContain('Digital Menu / Ordering URL');
        expect(manageHtml).toContain('Venue Event &amp; Announcement Banner');
        expect(manageHtml).toContain('Featured "Guru Picks" / House Specials');
    });

    test('fetchApi mock handles /cafe/update and /cafe/meta with menu_url, announcement_banner, and featured_game_ids', async () => {
        const payload = {
            cafe_id: 'the-malt-and-meeple',
            name: 'The Malt & Meeple',
            menu_url: 'https://toasttab.com/malt-and-meeple/menu',
            announcement_banner: '🎉 Trivia Night tonight at 7:30 PM! $5 craft pints on tap',
            featured_game_ids: ['13', '266192', '178900']
        };

        const res = await window.fetchApi('/cafe/update', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        expect(res.ok).toBe(true);
        const data = await res.json();
        expect(data.cafe.menu_url).toBe('https://toasttab.com/malt-and-meeple/menu');
        expect(data.cafe.announcement_banner).toBe('🎉 Trivia Night tonight at 7:30 PM! $5 craft pints on tap');
        expect(data.cafe.featured_game_ids).toEqual(['13', '266192', '178900']);

        // Verify retrieval via /cafe/meta
        const metaRes = await window.fetchApi('/cafe/meta?cafe_id=the-malt-and-meeple');
        expect(metaRes.ok).toBe(true);
        const metaData = await metaRes.json();
        expect(metaData.menu_url).toBe('https://toasttab.com/malt-and-meeple/menu');
        expect(metaData.announcement_banner).toBe('🎉 Trivia Night tonight at 7:30 PM! $5 craft pints on tap');
        expect(metaData.featured_game_ids).toEqual(['13', '266192', '178900']);
    });
});
