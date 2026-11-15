// Uses Vitest globals (configured via vitest.config.js globals: true) to avoid Windows drive-letter ESM/runner split
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

describe('safeDecode', () => {
  test('decodes standard URL encoded strings with spaces', () => {
    expect(window.safeDecode('The%20Den')).toBe('The Den');
    expect(window.safeDecode('The%20Vault')).toBe('The Vault');
  });

  test('decodes nested/double-encoded URL strings (%2520 -> space)', () => {
    expect(window.safeDecode('The%2520Den')).toBe('The Den');
    expect(window.safeDecode('The%252520Den')).toBe('The Den');
  });

  test('preserves already clean strings and handles edge cases', () => {
    expect(window.safeDecode('The Den')).toBe('The Den');
    expect(window.safeDecode('')).toBe('');
    expect(window.safeDecode(null)).toBe('');
    expect(window.safeDecode(undefined)).toBe('');
    expect(window.safeDecode('5')).toBe('5');
    expect(window.safeDecode('50% Off')).toBe('50% Off');
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

    expect(html).not.toContain('Match #');
    expect(html).toContain('Gloomhaven');
    expect(html).toContain('https://boardgamegeek.com/boardgame/12345');
    expect(container.textContent).toContain('★ 8.8');
    expect(container.textContent).toContain('⚙ 3.9/5');
    expect(container.textContent).toContain('👥 1-4 Players');
    expect(container.textContent).toContain('🕒 60-150 Min');
    expect(container.textContent).toContain('2017');
    expect(html).toContain('year-badge');
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

    expect(html).not.toContain('Match #');
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

  test('renders member affinities correctly when present', () => {
    const rec = {
      id: '12345',
      name: 'Gloomhaven',
      reason: 'Great cooperative game.',
      member_affinities: {
        alice: 0.45,
        bob: 0.18,
        charlie: 0.52
      }
    };

    const html = window.renderRecommendationCard(rec, 0);
    const container = document.createElement('div');
    container.innerHTML = html;

    expect(html).toContain('member-affinities-container');
    expect(html).toContain('Group Member Taste Alignment:');
    expect(container.textContent).toContain('alice');
    expect(container.textContent).toContain('bob');
    expect(container.textContent).toContain('charlie');
    
    expect(container.textContent).toContain('90%');
    expect(container.textContent).toContain('36%');
    expect(container.textContent).toContain('100%');
    
    expect(html).toContain('linear-gradient(90deg, #10b981, #34d399)');
    expect(html).toContain('linear-gradient(90deg, #ef4444, #f87171)');
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

describe('Password Complexity Validator (validatePassword)', () => {
  test('rejects empty, null, or short passwords', () => {
    expect(window.validatePassword('')).toContain('at least 8 characters');
    expect(window.validatePassword(null)).toContain('at least 8 characters');
    expect(window.validatePassword(undefined)).toContain('at least 8 characters');
    expect(window.validatePassword('Ab1!')).toContain('at least 8 characters');
  });

  test('rejects passwords missing an uppercase letter', () => {
    expect(window.validatePassword('lowercase123!')).toContain('uppercase letter');
  });

  test('rejects passwords missing a lowercase letter', () => {
    expect(window.validatePassword('UPPERCASE123!')).toContain('lowercase letter');
  });

  test('rejects passwords missing a number', () => {
    expect(window.validatePassword('NoNumbersHere!')).toContain('number');
  });

  test('rejects passwords missing a symbol', () => {
    expect(window.validatePassword('NoSymbols1234')).toContain('symbol or special character');
  });

  test('accepts compliant passwords', () => {
    expect(window.validatePassword('ValidPass123!')).toBeNull();
    expect(window.validatePassword('Secure#2026_Boardgame')).toBeNull();
  });
});

describe('Password Reset & Recovery Auth Flow', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('Auth.forgotPassword sends correct Cognito payload', async () => {
    const cognitoSpy = vi.spyOn(window.Auth, 'cognitoRequest').mockResolvedValue({
      CodeDeliveryDetails: { Destination: 'u***@example.com' }
    });

    const result = await window.Auth.forgotPassword('user@example.com');
    expect(cognitoSpy).toHaveBeenCalledWith('AWSCognitoIdentityProviderService.ForgotPassword', {
      ClientId: 'mock-client-id',
      Username: 'user@example.com'
    });
    expect(result.CodeDeliveryDetails.Destination).toBe('u***@example.com');
  });

  test('Auth.confirmForgotPassword sends correct confirmation payload', async () => {
    const cognitoSpy = vi.spyOn(window.Auth, 'cognitoRequest').mockResolvedValue({});

    await window.Auth.confirmForgotPassword('user@example.com', '123456', 'NewPass123!');
    expect(cognitoSpy).toHaveBeenCalledWith('AWSCognitoIdentityProviderService.ConfirmForgotPassword', {
      ClientId: 'mock-client-id',
      Username: 'user@example.com',
      ConfirmationCode: '123456',
      Password: 'NewPass123!'
    });
  });

  test('cognitoRequest parses error code from namespaced __type', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        __type: 'com.amazonaws.cognito.identity.idp.model#CodeMismatchException',
        message: 'Invalid code provided'
      })
    });

    await expect(window.Auth.forgotPassword('test@example.com')).rejects.toMatchObject({
      code: 'CodeMismatchException',
      message: 'Invalid code provided'
    });
  });

  test('cognitoRequest parses error code from simple __type', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        __type: 'UserNotFoundException',
        message: 'User does not exist'
      })
    });

    await expect(window.Auth.forgotPassword('nonexistent@example.com')).rejects.toMatchObject({
      code: 'UserNotFoundException',
      message: 'User does not exist'
    });
  });
});

describe('friendlyResetError mapping', () => {
  test('maps known Cognito error codes correctly', () => {
    expect(window.friendlyResetError({ code: 'UserNotFoundException' })).toBe(
      'No account found with that email address.'
    );
    expect(window.friendlyResetError({ code: 'CodeMismatchException' })).toBe(
      'The verification code is incorrect. Please check and try again.'
    );
    expect(window.friendlyResetError({ code: 'ExpiredCodeException' })).toBe(
      'This verification code has expired. Please request a new one.'
    );
    expect(window.friendlyResetError({ code: 'LimitExceededException' })).toBe(
      'Too many attempts. Please wait a few minutes before trying again.'
    );
    expect(window.friendlyResetError({ code: 'InvalidPasswordException' })).toBe(
      'Password does not meet the requirements (min 8 chars, uppercase, lowercase, number, symbol).'
    );
    expect(window.friendlyResetError({ code: 'InvalidParameterException' })).toBe(
      'Please check your input and try again.'
    );
  });

  test('falls back to error message or default text', () => {
    expect(window.friendlyResetError({ message: 'Custom network failure' })).toBe('Custom network failure');
    expect(window.friendlyResetError({})).toBe('Something went wrong. Please try again.');
    expect(window.friendlyResetError(null)).toBe('Something went wrong. Please try again.');
  });
});

describe('Rules Video Tutorial & Teach Time Integration', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  test('renderRecommendationCard renders How to Play button and teach time badge', () => {
    const rec = {
      id: '13',
      name: 'Catan',
      rating: 7.2,
      complexity: 2.3,
      rules_video_url: 'https://www.youtube.com/watch?v=wip12345678',
      teach_time: '10 min teach'
    };

    const html = window.renderRecommendationCard(rec, 0);
    const container = document.createElement('div');
    container.innerHTML = html;

    expect(html).toContain('btn-watch-rules');
    expect(html).toContain('🎬 How to Play');
    expect(html).toContain('data-game-id="13"');
    expect(html).toContain('data-game-name="Catan"');
    expect(html).toContain('data-video-url="https://www.youtube.com/watch?v=wip12345678"');
    expect(container.textContent).toContain('⏱ 10 min teach');
    expect(html).toContain('teach-time');
    expect(html).toContain('btn-bgg-link');
  });

  test('extractYouTubeId extracts valid 11-char video IDs from multiple formats', () => {
    expect(window.extractYouTubeId('https://www.youtube.com/watch?v=lgDgcLI2B0U')).toBe('lgDgcLI2B0U');
    expect(window.extractYouTubeId('https://youtu.be/zQVHkl8oQEU')).toBe('zQVHkl8oQEU');
    expect(window.extractYouTubeId('https://www.youtube.com/embed/yflGY5bW_1g')).toBe('yflGY5bW_1g');
    expect(window.extractYouTubeId('https://www.youtube.com/watch?feature=shared&v=68E6G9vP_xM')).toBe('68E6G9vP_xM');
    expect(window.extractYouTubeId('https://vimeo.com/12345678')).toBeNull();
    expect(window.extractYouTubeId('')).toBeNull();
    expect(window.extractYouTubeId(null)).toBeNull();
  });

  test('estimateTeachTime maps complexity ranges to friendly duration descriptions', () => {
    expect(window.estimateTeachTime(1.2)).toBe('3-5 min teach');
    expect(window.estimateTeachTime(2.1)).toBe('5-10 min teach');
    expect(window.estimateTeachTime(2.8)).toBe('10-15 min teach');
    expect(window.estimateTeachTime(3.6)).toBe('15-20 min teach');
    expect(window.estimateTeachTime(4.4)).toBe('20-30 min teach');
    expect(window.estimateTeachTime('invalid')).toBe('5-10 min teach');
  });

  test('openRulesVideoModal opens modal and populates YouTube iframe for valid video URL', () => {
    const game = {
      id: '230802',
      name: 'Azul',
      complexity: 1.8,
      teach_time: '5 min teach',
      rules_video_url: 'https://www.youtube.com/watch?v=yflGY5bW_1g'
    };

    window.openRulesVideoModal(game);

    const modal = document.getElementById('rules-video-modal');
    const title = document.getElementById('modal-game-title');
    const iframe = document.getElementById('rules-video-iframe');
    const videoContainer = document.getElementById('video-player-container');
    const fallbackNotice = document.getElementById('video-fallback-notice');
    const teachTime = document.getElementById('modal-teach-time');

    expect(modal).not.toBeNull();
    expect(modal.style.display).toBe('flex');
    expect(title.textContent).toBe('Azul');
    expect(teachTime.textContent).toContain('5 min teach');
    expect(videoContainer.style.display).toBe('block');
    expect(fallbackNotice.style.display).toBe('none');
    expect(iframe.src).toContain('https://www.youtube-nocookie.com/embed/yflGY5bW_1g');
  });

  test('openRulesVideoModal falls back gracefully to YouTube search when no video URL exists', () => {
    const game = {
      id: '99999',
      name: 'Obscure Game',
      complexity: 2.5,
      rules_video_url: null
    };

    window.openRulesVideoModal(game);

    const modal = document.getElementById('rules-video-modal');
    const iframe = document.getElementById('rules-video-iframe');
    const videoContainer = document.getElementById('video-player-container');
    const fallbackNotice = document.getElementById('video-fallback-notice');
    const searchLink = document.getElementById('video-external-search-link');

    expect(modal.style.display).toBe('flex');
    expect(videoContainer.style.display).toBe('none');
    expect(fallbackNotice.style.display).toBe('block');
    expect(searchLink.href).toContain('youtube.com/results?search_query=');
    expect(searchLink.href).toContain('Obscure%20Game');
    expect(iframe.src).toBe('');
    expect(iframe.getAttribute('src')).toBeNull();
  });

  test('openRulesVideoModal clears prior iframe src when switching to a game without a video URL', () => {
    window.openRulesVideoModal({
      id: '13',
      name: 'Catan',
      rules_video_url: 'https://www.youtube.com/watch?v=wip12345678'
    });

    const iframe = document.getElementById('rules-video-iframe');
    expect(iframe.src).toContain('wip12345678');

    window.openRulesVideoModal({
      id: '99999',
      name: 'Obscure Game'
    });

    expect(iframe.src).toBe('');
    expect(iframe.getAttribute('src')).toBeNull();
  });

  test('closeRulesVideoModal hides modal and resets iframe src', () => {
    const game = {
      id: '13',
      name: 'Catan',
      rules_video_url: 'https://www.youtube.com/watch?v=wip12345678'
    };

    window.openRulesVideoModal(game);
    const modal = document.getElementById('rules-video-modal');
    const iframe = document.getElementById('rules-video-iframe');

    expect(modal.style.display).toBe('flex');
    expect(iframe.src).toContain('wip12345678');

    window.closeRulesVideoModal();

    expect(modal.style.display).toBe('none');
    expect(iframe.src).not.toContain('wip12345678');
  });

  test('clicking .btn-watch-rules opens the video modal via event delegation', () => {
    const rec = {
      id: '266192',
      name: 'Wingspan',
      complexity: 2.4,
      rules_video_url: 'https://www.youtube.com/watch?v=lgDgcLI2B0U'
    };

    const container = document.createElement('div');
    container.innerHTML = window.renderRecommendationCard(rec, 0);
    document.body.appendChild(container);

    const watchBtn = container.querySelector('.btn-watch-rules');
    expect(watchBtn).not.toBeNull();

    watchBtn.click();

    const modal = document.getElementById('rules-video-modal');
    const title = document.getElementById('modal-game-title');
    const iframe = document.getElementById('rules-video-iframe');

    expect(modal.style.display).toBe('flex');
    expect(title.textContent).toBe('Wingspan');
    expect(iframe.src).toContain('lgDgcLI2B0U');
  });
});

