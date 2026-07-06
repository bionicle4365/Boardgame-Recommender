---
layout: null
---
// Boardgame Recommender - Shared JS Utilities

// Cognito configuration values compiled by Jekyll
const COGNITO_CLIENT_ID = "{{ site.cognito_client_id }}";
const COGNITO_REGION = "{{ site.cognito_region }}";

// Authentication Helper Methods
window.Auth = {
    isLoggedIn() {
        return !!localStorage.getItem("bgg_auth_id_token");
    },
    async getValidToken() {
        const idToken = localStorage.getItem("bgg_auth_id_token");
        const expiry = localStorage.getItem("bgg_auth_token_expiry");
        const refreshToken = localStorage.getItem("bgg_auth_refresh_token");
        
        if (!idToken || !refreshToken) return null;
        
        // Refresh token 5 minutes before expiry
        if (Date.now() > (parseInt(expiry) - 5 * 60 * 1000)) {
            try {
                const res = await this.cognitoRequest("AWSCognitoIdentityProviderService.InitiateAuth", {
                    ClientId: COGNITO_CLIENT_ID,
                    AuthFlow: "REFRESH_TOKEN_AUTH",
                    AuthParameters: {
                        REFRESH_TOKEN: refreshToken
                    }
                });
                if (res.AuthenticationResult) {
                    const newId = res.AuthenticationResult.IdToken;
                    localStorage.setItem("bgg_auth_id_token", newId);
                    localStorage.setItem("bgg_auth_token_expiry", (Date.now() + 3600 * 1000).toString());
                    return newId;
                }
            } catch (e) {
                console.error("Token refresh failed:", e);
                this.logout();
                return null;
            }
        }
        return idToken;
    },
    getEmail() {
        return localStorage.getItem("bgg_auth_email");
    },
    logout() {
        localStorage.removeItem("bgg_auth_id_token");
        localStorage.removeItem("bgg_auth_refresh_token");
        localStorage.removeItem("bgg_auth_email");
        localStorage.removeItem("bgg_auth_token_expiry");
        window.location.reload();
    },
    async cognitoRequest(target, payload) {
        const url = `https://cognito-idp.${COGNITO_REGION}.amazonaws.com/`;
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": target
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || "Cognito request failed");
        }
        return data;
    }
};

// API Fetch Wrapper
window.fetchApi = async function(endpoint, options = {}) {
    const apiUrl = "{{ site.api_url }}";
    
    // Developer helper: Mock API responses locally if API URL is a placeholder
    if (apiUrl === "PLACEHOLDER_API_URL") {
        console.log(`[Mock API] Intercepted request for ${endpoint}`);
        let data;
        if (endpoint.startsWith('/conventions')) {
            data = [
                { "convention_id": "gencon-2026", "name": "Gen Con 2026" },
                { "convention_id": "essen-2026", "name": "Essen Spiel 2026" }
            ];
        } else if (endpoint.startsWith('/recommendations')) {
            data = {
                status: "ready",
                recommendations: [
                    {
                        id: "224517",
                        name: "Gloomhaven",
                        thumbnail: "https://cf.geekdo-images.com/sZYp_3BTjrc47t9tM9vBvg__thumb/img/L-92966Zg7xS0F8B-UshZk1917A=/fit-in/200x150/filters:strip_icc()/pic2437871.jpg",
                        rating: 8.7,
                        complexity: 4.4,
                        min_players: 1,
                        max_players: 4,
                        playing_time: 120,
                        year_published: 2017,
                        reason: "Matches your taste for highly strategic tactical play and rich campaign elements."
                    },
                    {
                        id: "266192",
                        name: "Wingspan",
                        thumbnail: "https://cf.geekdo-images.com/yLZ_RQQH7OJeY0ZTO25y5A__thumb/img/4nOFLn4e75E7v9gN8GgdFj8z1v0=/fit-in/200x150/filters:strip_icc()/pic4458123.jpg",
                        rating: 8.1,
                        complexity: 2.4,
                        min_players: 1,
                        max_players: 5,
                        playing_time: 60,
                        year_published: 2019,
                        reason: "Excellent match for your preference of engine-building card games with smooth turns."
                    }
                ]
            };
        } else if (endpoint.startsWith('/preferences')) {
            data = {
                username: "MockUser",
                weights: { mechanics: 50, categories: 50, popularity: 50, hotness: 50 }
            };
        } else {
            data = {};
        }
        
        return {
            ok: true,
            status: 200,
            json: async () => data
        };
    }

    const url = endpoint.startsWith("http") ? endpoint : `${apiUrl}${endpoint}`;
    
    options.headers = options.headers || {};
    
    if (window.Auth && window.Auth.isLoggedIn()) {
        const token = await window.Auth.getValidToken();
        if (token) {
            options.headers["Authorization"] = `Bearer ${token}`;
        }
    }
    
    return fetch(url, options);
};

// XSS Sanitizer
window.escapeHTML = function(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
};

// Recommendation Card HTML Generator
window.renderRecommendationCard = function(rec, index, isPending = false) {
    const gameLink = rec.id 
        ? `https://boardgamegeek.com/boardgame/${rec.id}` 
        : `https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q=${encodeURIComponent(rec.name)}`;
    
    let statsHtml = "";
    if (rec.rating) {
        statsHtml += `
            <span class="stat-badge rating" title="BGG Geek Rating (Bayesian Average)">
                <span style="color: #b45309; font-weight: bold; margin-right: 2px;">★</span> ${rec.rating.toFixed(1)}
            </span>`;
    }
    if (rec.complexity) {
        statsHtml += `
            <span class="stat-badge complexity" title="Weight / Complexity (1.0 = Lightest, 5.0 = Heaviest)">
                <span style="color: #86198f; font-weight: bold; margin-right: 2px;">⚙</span> ${rec.complexity.toFixed(1)}/5
            </span>`;
    }
    if (rec.min_players && rec.max_players) {
        const playersStr = rec.min_players === rec.max_players ? `${rec.min_players}` : `${rec.min_players}-${rec.max_players}`;
        statsHtml += `
            <span class="stat-badge players" title="Supported Player Count">
                <span style="color: #15803d; font-weight: bold; margin-right: 2px;">👥</span> ${playersStr} Players
            </span>`;
    }
    if (rec.playing_time || (rec.min_playtime && rec.max_playtime)) {
        let playStr = "";
        if (rec.min_playtime && rec.max_playtime && rec.min_playtime !== rec.max_playtime) {
            playStr = `${rec.min_playtime}-${rec.max_playtime}`;
        } else {
            playStr = `${rec.playing_time || rec.min_playtime}`;
        }
        statsHtml += `
            <span class="stat-badge playtime" title="Estimated Playing Time">
                <span style="color: #0369a1; font-weight: bold; margin-right: 2px;">🕒</span> ${playStr} Min
            </span>`;
    }
    if (rec.year_published) {
        statsHtml += `
            <span class="stat-badge year" title="Year Published">
                <span style="color: #475569; font-weight: bold; margin-right: 2px;">📅</span> ${rec.year_published}
            </span>`;
    }

    const thumbUrl = rec.thumbnail || "https://cf.geekdo-images.com/images/placeholder_thumb.png";
    const loadingClass = isPending ? "loading" : "";
    
    return `
        <div class="rec-card" style="animation-delay: ${index * 0.05}s;">
            <div class="rec-card-body">
                <div class="rec-card-thumbnail">
                    <img src="${thumbUrl}" alt="${window.escapeHTML(rec.name)}" loading="lazy" onerror="this.onerror=null; this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png';">
                </div>
                <div class="rec-card-content">
                    <div class="rec-card-header">
                        <a href="${gameLink}" target="_blank" class="rec-title">${window.escapeHTML(rec.name)}</a>
                        <span class="badge">Match #${index + 1}</span>
                    </div>
                    <div class="rec-stats-container">
                        ${statsHtml}
                    </div>
                    <p class="rec-reason ${loadingClass}" data-game-id="${rec.id || ''}">${window.escapeHTML(rec.reason)}</p>
                </div>
            </div>
        </div>
    `;
};

// Render Skeleton Cards placeholder
window.renderSkeletonCards = function(container, count = 4) {
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `
            <div class="rec-card skeleton-card-placeholder">
                <div class="rec-card-body" style="display: flex; gap: 20px; flex-direction: row; align-items: flex-start;">
                    <div class="skeleton skeleton-avatar"></div>
                    <div class="rec-card-content" style="flex-grow: 1; display: flex; flex-direction: column; gap: 8px;">
                        <div class="rec-card-header" style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; width: 100%;">
                            <div class="skeleton skeleton-text title" style="width: 50%; height: 20px; margin: 0;"></div>
                            <div class="skeleton skeleton-text" style="width: 80px; height: 20px; border-radius: 9999px; margin: 0;"></div>
                        </div>
                        <div class="rec-stats-container" style="display: flex; gap: 8px; margin-top: 2px; margin-bottom: 6px; flex-wrap: wrap;">
                            <div class="skeleton skeleton-text" style="width: 60px; height: 24px; border-radius: 6px; margin: 0;"></div>
                            <div class="skeleton skeleton-text" style="width: 80px; height: 24px; border-radius: 6px; margin: 0;"></div>
                            <div class="skeleton skeleton-text" style="width: 90px; height: 24px; border-radius: 6px; margin: 0;"></div>
                        </div>
                        <div class="skeleton skeleton-text paragraph" style="width: 100%; height: 50px; border-radius: 4px; margin-top: 12px;"></div>
                    </div>
                </div>
            </div>
        `;
    }
    container.innerHTML = html;
};
