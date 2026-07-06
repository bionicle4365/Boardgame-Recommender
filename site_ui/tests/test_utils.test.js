import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import fs from 'fs';
import path from 'path';

// Setup environment and load utils.js
const utilsJsPath = path.resolve(__dirname, '../assets/js/utils.js');
let rawCode = fs.readFileSync(utilsJsPath, 'utf8');

// Preprocess Jekyll code to clean JavaScript
// 1. Strip the frontmatter blocks at the beginning of the file
let code = rawCode.replace(/^---[\s\S]*?---/, '');
// 2. Replace Jekyll variables with static string configuration
code = code.replace(/"\{\{\s*site\.cognito_client_id\s*\}\}"/g, '"mock-client-id"');
code = code.replace(/"\{\{\s*site\.cognito_region\s*\}\}"/g, '"us-east-1"');
code = code.replace(/"\{\{\s*site\.api_url\s*\}\}"/g, '"https://api.mock.com"');

// Execute code to populate window/global scope in JSDOM
// JSDOM creates window, document, localStorage in the global scope when Vitest runs with environment: 'jsdom'
eval(code);

describe('escapeHTML', () => {
  test('escapes special HTML characters', () => {
    expect(window.escapeHTML('&')).toBe('&amp;');
    expect(window.escapeHTML('<')).toBe('&lt;');
    expect(window.escapeHTML('>')).toBe('&gt;');
    expect(window.escapeHTML('"')).toBe('&quot;');
    expect(window.escapeHTML("'")).toBe('&#039;');
  });

  test('handles empty or null values', () => {
    expect(window.escapeHTML('')).toBe('');
    expect(window.escapeHTML(null)).toBe('');
    expect(window.escapeHTML(undefined)).toBe('');
  });

  test('converts numbers and other types to escaped strings', () => {
    expect(window.escapeHTML(123)).toBe('123');
  });
});

describe('renderRecommendationCard', () => {
  test('renders full stats correctly', () => {
    const rec = {
      id: '12345',
      name: 'Gloomhaven',
      rating: 8.7654,
      complexity: 3.85,
      min_players: 1,
      max_players: 4,
      playing_time: 120,
      min_playtime: 60,
      max_playtime: 150,
      year_published: 2017,
      thumbnail: 'https://images.com/gloomhaven.jpg',
      reason: 'It matches your love for tactical combat.'
    };

    const html = window.renderRecommendationCard(rec, 0);
    const container = document.createElement('div');
    container.innerHTML = html;

    expect(html).toContain('Match #1');
    expect(html).toContain('Gloomhaven');
    expect(html).toContain('https://boardgamegeek.com/boardgame/12345');
    expect(container.textContent).toContain('★ 8.8');
    expect(container.textContent).toContain('⚙ 3.9/5');
    expect(container.textContent).toContain('👥 1-4 Players');
    expect(container.textContent).toContain('🕒 60-150 Min');
    expect(container.textContent).toContain('📅 2017');
    expect(html).toContain('It matches your love for tactical combat.');
    expect(html).toContain('https://images.com/gloomhaven.jpg');
  });

  test('renders single player count and single play time stats', () => {
    const rec = {
      id: '99',
      name: 'Chess',
      min_players: 2,
      max_players: 2,
      playing_time: 60,
      reason: 'Classic strategy'
    };

    const html = window.renderRecommendationCard(rec, 1);
    const container = document.createElement('div');
    container.innerHTML = html;

    expect(html).toContain('Match #2');
    expect(html).toContain('Chess');
    expect(container.textContent).toContain('👥 2 Players');
    expect(container.textContent).toContain('🕒 60 Min');
  });

  test('falls back gracefully on missing values', () => {
    const rec = {
      name: 'Mystery Game',
      reason: 'No metadata exists.'
    };

    const html = window.renderRecommendationCard(rec, 2);
    expect(html).toContain('Mystery Game');
    expect(html).toContain('geeksearch.php?action=search');
    expect(html).not.toContain('★');
    expect(html).not.toContain('⚙');
    expect(html).not.toContain('Players');
    expect(html).not.toContain('Min');
    expect(html).not.toContain('📅');
    expect(html).toContain('placeholder_thumb.png');
  });
});

describe('renderSkeletonCards', () => {
  test('adds the requested number of skeleton cards', () => {
    const container = document.createElement('div');
    window.renderSkeletonCards(container, 3);
    
    const cards = container.querySelectorAll('.skeleton-card-placeholder');
    expect(cards.length).toBe(3);
  });
});

describe('Auth Helper Module', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    localStorage.clear();
    // Mock window.location.reload
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { reload: vi.fn() },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
    vi.restoreAllMocks();
  });

  test('isLoggedIn returns false when token is missing', () => {
    expect(window.Auth.isLoggedIn()).toBe(false);
  });

  test('isLoggedIn returns true when token is present', () => {
    localStorage.setItem('bgg_auth_id_token', 'mock-token');
    expect(window.Auth.isLoggedIn()).toBe(true);
  });

  test('getEmail retrieves email from localStorage', () => {
    localStorage.setItem('bgg_auth_email', 'test@example.com');
    expect(window.Auth.getEmail()).toBe('test@example.com');
  });

  test('logout clears localStorage and reloads', () => {
    localStorage.setItem('bgg_auth_id_token', 'tok');
    localStorage.setItem('bgg_auth_email', 'mail');
    
    window.Auth.logout();
    
    expect(localStorage.getItem('bgg_auth_id_token')).toBeNull();
    expect(localStorage.getItem('bgg_auth_email')).toBeNull();
    expect(window.location.reload).toHaveBeenCalledOnce();
  });

  test('getValidToken returns null if no token is stored', async () => {
    const token = await window.Auth.getValidToken();
    expect(token).toBeNull();
  });

  test('getValidToken returns existing token if it is fresh', async () => {
    localStorage.setItem('bgg_auth_id_token', 'fresh-token');
    localStorage.setItem('bgg_auth_refresh_token', 'refresh');
    // Set expiry 10 minutes in the future
    localStorage.setItem('bgg_auth_token_expiry', (Date.now() + 10 * 60 * 1000).toString());

    const token = await window.Auth.getValidToken();
    expect(token).toBe('fresh-token');
  });

  test('getValidToken refreshes token if it is close to expiry', async () => {
    localStorage.setItem('bgg_auth_id_token', 'old-token');
    localStorage.setItem('bgg_auth_refresh_token', 'my-refresh-token');
    // Set expiry 3 minutes in the future (less than 5 min threshold)
    localStorage.setItem('bgg_auth_token_expiry', (Date.now() + 3 * 60 * 1000).toString());

    const cognitoSpy = vi.spyOn(window.Auth, 'cognitoRequest').mockResolvedValue({
      AuthenticationResult: {
        IdToken: 'new-id-token'
      }
    });

    const token = await window.Auth.getValidToken();
    expect(cognitoSpy).toHaveBeenCalledWith('AWSCognitoIdentityProviderService.InitiateAuth', {
      ClientId: 'mock-client-id',
      AuthFlow: 'REFRESH_TOKEN_AUTH',
      AuthParameters: {
        REFRESH_TOKEN: 'my-refresh-token'
      }
    });
    expect(token).toBe('new-id-token');
    expect(localStorage.getItem('bgg_auth_id_token')).toBe('new-id-token');
  });

  test('getValidToken logs out if refresh fails', async () => {
    localStorage.setItem('bgg_auth_id_token', 'old-token');
    localStorage.setItem('bgg_auth_refresh_token', 'my-refresh-token');
    localStorage.setItem('bgg_auth_token_expiry', (Date.now() + 3 * 60 * 1000).toString());

    vi.spyOn(window.Auth, 'cognitoRequest').mockRejectedValue(new Error('Network error'));
    const logoutSpy = vi.spyOn(window.Auth, 'logout').mockImplementation(() => {});

    const token = await window.Auth.getValidToken();
    expect(token).toBeNull();
    expect(logoutSpy).toHaveBeenCalledOnce();
  });
});

describe('fetchApi', () => {
  beforeEach(() => {
    localStorage.clear();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true })
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('calls fetch with full URL', async () => {
    await window.fetchApi('/recommendations');
    expect(global.fetch).toHaveBeenCalledWith('https://api.mock.com/recommendations', expect.any(Object));
  });

  test('accepts absolute URLs directly', async () => {
    await window.fetchApi('https://other-api.com/status');
    expect(global.fetch).toHaveBeenCalledWith('https://other-api.com/status', expect.any(Object));
  });

  test('includes auth headers when logged in', async () => {
    localStorage.setItem('bgg_auth_id_token', 'my-token');
    localStorage.setItem('bgg_auth_refresh_token', 'ref');
    // Set expiry far in future
    localStorage.setItem('bgg_auth_token_expiry', (Date.now() + 60 * 60 * 1000).toString());

    await window.fetchApi('/recommendations');
    expect(global.fetch).toHaveBeenCalledWith('https://api.mock.com/recommendations', {
      headers: {
        'Authorization': 'Bearer my-token'
      }
    });
  });
});
