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
    getBggUsername() {
        return (localStorage.getItem("bgg_username") || 
                localStorage.getItem("bgg_last_username") || 
                "").trim();
    },
    setBggUsername(username) {
        if (username && String(username).trim()) {
            const clean = String(username).trim();
            localStorage.setItem("bgg_username", clean);
            localStorage.setItem("bgg_last_username", clean);
        }
    },
    logout() {
        localStorage.removeItem("bgg_auth_id_token");
        localStorage.removeItem("bgg_auth_refresh_token");
        localStorage.removeItem("bgg_auth_email");
        localStorage.removeItem("bgg_auth_token_expiry");
        window.location.reload();
    },
    async cognitoRequest(target, payload) {
        // Developer helper: Mock Cognito responses locally if Client ID is a placeholder
        if (COGNITO_CLIENT_ID === "PLACEHOLDER_COGNITO_CLIENT_ID") {
            console.log(`[Mock Cognito] Intercepted request for ${target}`, payload);
            if (target === "AWSCognitoIdentityProviderService.InitiateAuth") {
                return {
                    AuthenticationResult: {
                        IdToken: "mock_id_token_" + Date.now(),
                        RefreshToken: "mock_refresh_token_" + Date.now()
                    }
                };
            }
            if (target === "AWSCognitoIdentityProviderService.SignUp") {
                return { UserConfirmed: true };
            }
            if (target === "AWSCognitoIdentityProviderService.ForgotPassword") {
                return { CodeDeliveryDetails: { Destination: payload.Username } };
            }
            if (target === "AWSCognitoIdentityProviderService.ConfirmForgotPassword") {
                if (payload.ConfirmationCode !== "123456") {
                    const err = new Error("Invalid verification code provided, please try again.");
                    err.code = "CodeMismatchException";
                    throw err;
                }
                return {};
            }
        }

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
            const err = new Error(data.message || "Cognito request failed");
            if (data.__type) {
                err.code = data.__type.split("#").pop();
            }
            throw err;
        }
        return data;
    },
    async forgotPassword(email) {
        return this.cognitoRequest("AWSCognitoIdentityProviderService.ForgotPassword", {
            ClientId: COGNITO_CLIENT_ID,
            Username: email
        });
    },
    async confirmForgotPassword(email, code, newPassword) {
        return this.cognitoRequest("AWSCognitoIdentityProviderService.ConfirmForgotPassword", {
            ClientId: COGNITO_CLIENT_ID,
            Username: email,
            ConfirmationCode: code,
            Password: newPassword
        });
    }
};

// Password Complexity Validator (Cognito Policy: min 8 chars, uppercase, lowercase, number, symbol)
window.validatePassword = function(password) {
    if (!password || password.length < 8) {
        return "Password must be at least 8 characters long.";
    }
    if (!/[A-Z]/.test(password)) {
        return "Password must contain at least one uppercase letter.";
    }
    if (!/[a-z]/.test(password)) {
        return "Password must contain at least one lowercase letter.";
    }
    if (!/[0-9]/.test(password)) {
        return "Password must contain at least one number.";
    }
    if (!/[^A-Za-z0-9]/.test(password)) {
        return "Password must contain at least one symbol or special character.";
    }
    return null; // Valid
};

// Cognito Error Code to Friendly Message Mapper
window.friendlyResetError = function(err) {
    if (!err) return "Something went wrong. Please try again.";
    const code = err.code || "";
    switch (code) {
        case "UserNotFoundException":
            return "No account found with that email address.";
        case "CodeMismatchException":
            return "The verification code is incorrect. Please check and try again.";
        case "ExpiredCodeException":
            return "This verification code has expired. Please request a new one.";
        case "LimitExceededException":
            return "Too many attempts. Please wait a few minutes before trying again.";
        case "InvalidPasswordException":
            return "Password does not meet the requirements (min 8 chars, uppercase, lowercase, number, symbol).";
        case "InvalidParameterException":
            return "Please check your input and try again.";
        default:
            return err.message || "Something went wrong. Please try again.";
    }
};

// Shared Mock Cafe Catalog for local testing & demos
function getMockCafeCatalog() {
    return [
        {
            id: "295947",
            name: "Cascadia",
            thumbnail: "https://cf.geekdo-images.com/MJE673qOvyIfPkTviqUKGg__thumb/img/pic5100791.jpg",
            rating: 8.0,
            complexity: 2.0,
            min_players: 1,
            max_players: 4,
            playing_time: 45,
            year_published: 2021,
            shelf_location: "Shelf B-1",
            teach_time: "5 min teach",
            mechanics: ["Tile Placement", "Drafting", "Pattern Building"],
            categories: ["Animals", "Puzzle", "Environmental"],
            reason: "Accessible spatial tile-laying puzzle that is effortless to learn and relaxing to play."
        },
        {
            id: "178900",
            name: "Codenames",
            thumbnail: "https://cf.geekdo-images.com/F_KDEu0GjdUtMW-M5RDePg__thumb/img/6P8eD6_s17m3x5kK.jpg",
            rating: 7.6,
            complexity: 1.3,
            min_players: 2,
            max_players: 8,
            playing_time: 15,
            year_published: 2015,
            shelf_location: "Shelf A-1",
            teach_time: "3-5 min teach",
            mechanics: ["Word Play", "Memory", "Team-Based Game"],
            categories: ["Party Game", "Word Game", "Deduction"],
            reason: "High-energy word association that gets your table laughing and bantering right away."
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
            shelf_location: "Shelf B-3",
            teach_time: "10 min teach",
            mechanics: ["Engine Building", "Hand Management", "Card Drafting"],
            categories: ["Animals", "Card Game", "Economic"],
            reason: "Rewarding bird habitat engine building with smooth turns and gorgeous components."
        },
        {
            id: "230802",
            name: "Azul",
            thumbnail: "https://cf.geekdo-images.com/tz19Pf9klD_5.jpg",
            rating: 7.8,
            complexity: 1.8,
            min_players: 2,
            max_players: 4,
            playing_time: 30,
            year_published: 2017,
            shelf_location: "Shelf B-4",
            teach_time: "5 min teach",
            mechanics: ["Pattern Building", "Tile Placement", "Drafting"],
            categories: ["Abstract Strategy", "Puzzle"],
            reason: "Tactile tile-drafting masterpiece with crisp turns and satisfying pattern completion."
        },
        {
            id: "254640",
            name: "Just One",
            thumbnail: "https://cf.geekdo-images.com/ocwvx4_jL3e8q5p.jpg",
            rating: 7.5,
            complexity: 1.1,
            min_players: 3,
            max_players: 7,
            playing_time: 20,
            year_published: 2018,
            shelf_location: "Shelf A-2",
            teach_time: "2-3 min teach",
            mechanics: ["Cooperative Game", "Word Play", "Communication Limits"],
            categories: ["Party Game", "Word Game"],
            reason: "Effortless cooperative clue-giving that breaks the ice instantly for groups."
        },
        {
            id: "28720",
            name: "Brass: Birmingham",
            thumbnail: "https://cf.geekdo-images.com/sZYp_3BTjrc47t9tM9vBvg__thumb/img/L-92966Zg7xS0F8B-UshZk1917A=/fit-in/200x150/filters:strip_icc()/pic2437871.jpg",
            rating: 8.6,
            complexity: 3.9,
            min_players: 2,
            max_players: 4,
            playing_time: 120,
            year_published: 2018,
            shelf_location: "Shelf D-2",
            teach_time: "20 min teach",
            mechanics: ["Network Building", "Hand Management", "Market"],
            categories: ["Economic", "Industry", "Transportation"],
            reason: "Deep industrial network economics with satisfyingly tight tactical decisions."
        },
        {
            id: "316554",
            name: "Dune: Imperium",
            thumbnail: "https://cf.geekdo-images.com/sZYp_3BTjrc47t9tM9vBvg__thumb/img/pic5666597.jpg",
            rating: 8.4,
            complexity: 3.0,
            min_players: 1,
            max_players: 4,
            playing_time: 90,
            year_published: 2020,
            shelf_location: "Shelf D-4",
            teach_time: "15 min teach",
            mechanics: ["Deck Construction", "Worker Placement", "Area Majority"],
            categories: ["Science Fiction", "Political", "Space Exploration"],
            reason: "Tense deck-building and worker placement that keeps all players engaged until the final combat."
        },
        {
            id: "324856",
            name: "The Crew: Mission Deep Sea",
            thumbnail: "https://cf.geekdo-images.com/yLZ_RQQH7OJeY0ZTO25y5A__thumb/img/pic5758253.jpg",
            rating: 8.2,
            complexity: 2.0,
            min_players: 2,
            max_players: 5,
            playing_time: 20,
            year_published: 2021,
            shelf_location: "Shelf C-1",
            teach_time: "5 min teach",
            mechanics: ["Trick-taking", "Cooperative Game", "Communication Limits"],
            categories: ["Card Game", "Nautical"],
            reason: "Brilliant cooperative trick-taking with silent communication that bonds your table together."
        },
        {
            id: "30549",
            name: "Pandemic",
            thumbnail: "https://cf.geekdo-images.com/S3ybV1_xDY4BEID4.jpg",
            rating: 7.6,
            complexity: 2.4,
            min_players: 2,
            max_players: 4,
            playing_time: 45,
            year_published: 2008,
            shelf_location: "Shelf C-3",
            teach_time: "8 min teach",
            mechanics: ["Cooperative Game", "Point to Point Movement", "Set Collection"],
            categories: ["Medical", "Adventure"],
            reason: "Classic cooperative tension where everyone coordinates specialist roles to contain global outbreaks."
        },
        {
            id: "274637",
            name: "Unmatched: Battle of Legends",
            thumbnail: "https://cf.geekdo-images.com/pic4747471.jpg",
            rating: 7.9,
            complexity: 2.1,
            min_players: 2,
            max_players: 4,
            playing_time: 30,
            year_published: 2019,
            shelf_location: "Shelf E-1",
            teach_time: "5 min teach",
            mechanics: ["Hand Management", "Grid Movement", "Variable Player Powers"],
            categories: ["Fighting", "Fantasy", "Miniatures"],
            reason: "Fast, punchy card-driven skirmish duels with dynamic movement and clever bluffing."
        },
        {
            id: "13",
            name: "Catan",
            thumbnail: "https://cf.geekdo-images.com/W_ftXvnlGDPyqTm2UJKDxA__thumb/img/p8Jd_h_7L2A2q8p.jpg",
            rating: 7.1,
            complexity: 2.3,
            min_players: 3,
            max_players: 4,
            playing_time: 75,
            year_published: 1995,
            shelf_location: "Shelf A-3",
            teach_time: "10 min teach",
            mechanics: ["Trading", "Dice Rolling", "Network Building"],
            categories: ["Economic", "Negotiation"],
            reason: "The quintessential trade-and-build modern classic."
        },
        {
            id: "9209",
            name: "Ticket to Ride",
            thumbnail: "https://cf.geekdo-images.com/ZWJg0dCdrWHxVnc0eFXK8w__thumb/img/pic38668.jpg",
            rating: 7.4,
            complexity: 1.8,
            min_players: 2,
            max_players: 5,
            playing_time: 45,
            year_published: 2004,
            shelf_location: "Shelf B-2",
            teach_time: "5 min teach",
            mechanics: ["Set Collection", "Route Building", "Hand Management"],
            categories: ["Trains", "Family"],
            reason: "Cross-country train route building that everyone loves."
        },
        {
            id: "822",
            name: "Carcassonne",
            thumbnail: "https://cf.geekdo-images.com/okM0dq_bEXnbyQTOvHkw0w__thumb/img/pic6544250.png",
            rating: 7.4,
            complexity: 1.9,
            min_players: 2,
            max_players: 5,
            playing_time: 35,
            year_published: 2000,
            shelf_location: "Shelf B-5",
            teach_time: "5 min teach",
            mechanics: ["Tile Placement", "Area Majority"],
            categories: ["Medieval", "Territory Building"],
            reason: "Classic countryside tile-laying with castles, roads, and monasteries."
        },
        {
            id: "167791",
            name: "Terraforming Mars",
            thumbnail: "https://cf.geekdo-images.com/wg9oOLcsKvDesqruapstqA__thumb/img/pic3536616.jpg",
            rating: 8.4,
            complexity: 3.3,
            min_players: 1,
            max_players: 5,
            playing_time: 120,
            year_published: 2016,
            shelf_location: "Shelf D-1",
            teach_time: "15 min teach",
            mechanics: ["Engine Building", "Hand Management", "Drafting"],
            categories: ["Science Fiction", "Economic", "Space Exploration"],
            reason: "Transform the Red Planet into a thriving ecosystem."
        },
        {
            id: "329839",
            name: "Scout",
            thumbnail: "https://cf.geekdo-images.com/inbA0cE3_v03Q5U1n1X4Zw__thumb/img/pic6518179.jpg",
            rating: 7.8,
            complexity: 1.3,
            min_players: 2,
            max_players: 5,
            playing_time: 15,
            year_published: 2019,
            shelf_location: "",
            teach_time: "3 min teach",
            mechanics: ["Ladder Climbing", "Hand Management"],
            categories: ["Card Game", "Circus"],
            reason: "Ingenious ladder-climbing card game where you cannot rearrange cards in your hand."
        },
        {
            id: "129622",
            name: "Love Letter",
            thumbnail: "https://cf.geekdo-images.com/T1O22ZO2FdflwKYzNOtawg__thumb/img/pic1401448.jpg",
            rating: 7.2,
            complexity: 1.2,
            min_players: 2,
            max_players: 4,
            playing_time: 15,
            year_published: 2012,
            shelf_location: null,
            teach_time: "2 min teach",
            mechanics: ["Deduction", "Hand Management", "Player Elimination"],
            categories: ["Card Game", "Bluffing", "Renaissance"],
            reason: "16 cards, maximum deduction, risk, and bluffing."
        }
    ];
}

// API Fetch Wrapper
window.fetchApi = async function(endpoint, options = {}) {
    const apiUrl = "{{ site.api_url }}";
    
    // Developer helper: Mock API responses locally if API URL is a placeholder
    if (apiUrl === "PLACEHOLDER_API_URL") {
        console.log(`[Mock API] Intercepted request for ${endpoint}`);
        if (endpoint.startsWith('/collection')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1]);
            const username = urlParams.get('username') || '';
            const bggUrl = `https://boardgamegeek.com/xmlapi2/collection?username=${username}&stats=1`;
            console.log(`[Mock API] Redirecting /collection to real BGG: ${bggUrl}`);
            return fetch(bggUrl, options);
        }
        let data;
        if (endpoint.startsWith('/conventions')) {
            data = [
                { "convention_id": "spielessen2026", "name": "SPIEL Essen 2026", "date": "2026-10-25", "game_count": 1166 },
                { "convention_id": "paxunplugged2026", "name": "PAX Unplugged 2026 Preview", "date": "2026-12-06", "game_count": 135 }
            ];
        } else if (endpoint.startsWith('/cafe/collection')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            const cafeId = urlParams.get('cafe_id') || urlParams.get('slug') || 'demo-cafe';
            const catalog = getMockCafeCatalog();
            data = {
                status: "ready",
                cafe_id: cafeId,
                total: catalog.length,
                collection: catalog
            };
        } else if (endpoint.startsWith('/recommendations')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1]);
            const cafeIdParam = urlParams.get('cafe_id') || urlParams.get('cafe_username');
            const vibeParam = urlParams.get('vibe') || 'casual_strategy';
            const usernameParam = urlParams.get('username') || '';
            const users = usernameParam.split(',').filter(u => u.trim() !== '');
            let memberAffinities = null;
            if (users.length > 1) {
                memberAffinities = {};
                users.forEach((u, i) => {
                    memberAffinities[u] = parseFloat((0.4 + (i * 0.15) + (u.length % 5) * 0.08).toFixed(2));
                });
            }

            if (cafeIdParam) {
                let cafeRecs = [];
                const allGames = getMockCafeCatalog();
                if (vibeParam === 'all' || vibeParam === 'any') {
                    cafeRecs = allGames;
                } else if (vibeParam === 'party') {
                    cafeRecs = allGames.filter(g => ['178900', '254640', '13', '9209', '329839', '129622'].includes(g.id));
                } else if (vibeParam === 'deep_strategy') {
                    cafeRecs = allGames.filter(g => ['28720', '316554', '167791'].includes(g.id));
                } else if (vibeParam === 'cooperative') {
                    cafeRecs = allGames.filter(g => ['324856', '30549', '254640'].includes(g.id));
                } else if (vibeParam === 'direct_conflict') {
                    cafeRecs = allGames.filter(g => ['274637', '316554'].includes(g.id));
                } else {
                    // casual_strategy default
                    cafeRecs = allGames.filter(g => ['295947', '266192', '230802', '822', '13', '9209'].includes(g.id));
                }

                if (memberAffinities) {
                    cafeRecs = cafeRecs.map(r => ({ ...r, member_affinities: memberAffinities }));
                }

                data = {
                    status: "ready",
                    recommendations: cafeRecs
                };
            } else {
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
                            reason: "Matches your taste for highly strategic tactical play and rich campaign elements.",
                            member_affinities: memberAffinities
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
                            reason: "Excellent match for your preference of engine-building card games with smooth turns.",
                            member_affinities: memberAffinities
                        }
                    ]
                };
            }
        } else if (endpoint.startsWith('/preferences')) {
            if (options.method === 'POST' && options.body) {
                try {
                    const parsed = JSON.parse(options.body);
                    const existing = JSON.parse(localStorage.getItem('bgg_mock_preferences') || '{}');
                    const updated = { ...existing, ...parsed };
                    localStorage.setItem('bgg_mock_preferences', JSON.stringify(updated));
                    data = { message: "Preferences updated successfully", preferences: updated };
                } catch (e) {
                    data = { message: "Preferences updated" };
                }
            } else {
                const saved = JSON.parse(localStorage.getItem('bgg_mock_preferences') || '{}');
                data = {
                    bgg_username: saved.bgg_username || "gamer123",
                    weights: saved.weights || { mechanics: 50, categories: 50, popularity: 50, hotness: 50 }
                };
            }
        } else if (endpoint.startsWith('/groups')) {
            let groups = JSON.parse(localStorage.getItem('bgg_mock_groups') || 'null');
            if (!groups) {
                groups = [
                    { id: "grp-1", name: "Friday Heavy Euro", members: ["gamer123", "alice", "bob"] },
                    { id: "grp-2", name: "Weekend Casual", members: ["gamer123", "charlie"] }
                ];
                localStorage.setItem('bgg_mock_groups', JSON.stringify(groups));
            }
            if (options.method === 'POST' && options.body) {
                try {
                    const newGroup = JSON.parse(options.body);
                    newGroup.id = newGroup.id || `grp-${Date.now()}`;
                    const idx = groups.findIndex(g => g.id === newGroup.id);
                    if (idx >= 0) groups[idx] = newGroup;
                    else groups.push(newGroup);
                    localStorage.setItem('bgg_mock_groups', JSON.stringify(groups));
                    data = { message: "Group saved", group: newGroup };
                } catch (e) {
                    data = { message: "Group saved" };
                }
            } else if (options.method === 'DELETE') {
                const groupId = endpoint.split('/groups/')[1] || '';
                groups = groups.filter(g => g.id !== groupId);
                localStorage.setItem('bgg_mock_groups', JSON.stringify(groups));
                data = { message: "Group deleted" };
            } else {
                data = { groups };
            }
        } else if (endpoint.startsWith('/profile')) {
            data = {
                username: "gamer123",
                collection_size: 48,
                avg_rating: 7.8,
                complexity_pref: "Medium-Heavy",
                top_mechanics: { "Worker Placement": 0.85, "Hand Management": 0.72, "Deck Construction": 0.65, "Drafting": 0.58, "Variable Player Powers": 0.54 },
                top_categories: { "Economic": 0.82, "Fantasy": 0.70, "Science Fiction": 0.64, "Card Game": 0.60, "Medieval": 0.52 },
                complexity_weights: { "Light": 0.1, "Medium-Light": 0.3, "Medium-Heavy": 0.8, "Heavy": 0.5 },
                player_counts: { "1": 5, "2": 18, "3": 25, "4": 30, "5+": 12 },
                rating_distribution: { "1-4": 1, "5-6": 6, "7-8": 22, "9-10": 13 },
                generated_at: new Date().toISOString()
            };
        } else if (endpoint.startsWith('/sessions')) {
            const sessions = JSON.parse(localStorage.getItem('bgg_mock_sessions') || '[]');
            const now = new Date();
            sessions.forEach(s => {
                if (s.closes_at) s.is_closed = now >= new Date(s.closes_at);
                if (s.creator_name === 'anonymous_host') {
                    s.creator_name = (window.Auth && window.Auth.getBggUsername && window.Auth.getBggUsername()) || 'Host';
                }
            });
            data = { sessions };
        } else if (endpoint.startsWith('/session/vote') || (endpoint.startsWith('/session') && options.method === 'POST' && options.body && options.body.includes('participant_name'))) {
            let sessions = JSON.parse(localStorage.getItem('bgg_mock_sessions') || '[]');
            const payload = JSON.parse(options.body || '{}');
            const targetSession = sessions.find(s => s.session_id === payload.session_id);
            if (targetSession) {
                targetSession.votes = targetSession.votes || {};
                targetSession.votes[payload.participant_name] = payload.votes || {};
                
                // Recalculate consensus
                const totalVoters = Object.keys(targetSession.votes).length;
                const rankings = (targetSession.candidates || []).map((cand, idx) => {
                    let score = 0, yes = 0, neutral = 0, veto = 0;
                    const votersYes = [], votersNeutral = [], votersVeto = [];
                    Object.entries(targetSession.votes).forEach(([voter, b]) => {
                        const v = (b[cand.id] || 'neutral').toLowerCase();
                        if (v === 'yes') { score += 2; yes++; votersYes.push(voter); }
                        else if (v === 'neutral') { score += 1; neutral++; votersNeutral.push(voter); }
                        else if (v === 'veto') { score -= 99; veto++; votersVeto.push(voter); }
                    });
                    return {
                        id: String(cand.id),
                        name: cand.name,
                        original_rank: idx,
                        score,
                        yes_count: yes,
                        neutral_count: neutral,
                        veto_count: veto,
                        is_vetoed: veto > 0,
                        voters_yes: votersYes,
                        voters_neutral: votersNeutral,
                        voters_veto: votersVeto,
                        candidate: cand
                    };
                });
                rankings.sort((a, b) => (a.is_vetoed === b.is_vetoed ? b.score - a.score || a.original_rank - b.original_rank : a.is_vetoed ? 1 : -1));
                targetSession.consensus = {
                    total_voters: totalVoters,
                    winner: rankings.length && !rankings[0].is_vetoed ? rankings[0].candidate : null,
                    rankings,
                    vetoed_games: rankings.filter(r => r.is_vetoed).map(r => r.id)
                };
                localStorage.setItem('bgg_mock_sessions', JSON.stringify(sessions));
                data = targetSession;
            } else {
                data = { error: "Session not found" };
            }
        } else if (endpoint.startsWith('/session/close') || (endpoint.startsWith('/session') && options.method === 'PUT')) {
            const payload = JSON.parse(options.body || '{}');
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            const sessionId = payload.session_id || urlParams.get('session_id') || urlParams.get('id');
            const sessions = JSON.parse(localStorage.getItem('bgg_mock_sessions') || '[]');
            const found = sessions.find(s => s.session_id === sessionId);
            if (found) {
                found.closes_at = new Date().toISOString();
                found.is_closed = true;
                localStorage.setItem('bgg_mock_sessions', JSON.stringify(sessions));
                data = found;
            } else {
                data = { error: "Session not found" };
            }
        } else if (endpoint.startsWith('/session/delete') || endpoint.startsWith('/session/cancel') || (endpoint.startsWith('/session') && options.method === 'DELETE')) {
            const payload = JSON.parse(options.body || '{}');
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            let sessionId = payload.session_id || urlParams.get('session_id') || urlParams.get('id');
            if (!sessionId) {
                const parts = endpoint.split('?')[0].split('/');
                if (parts.length > 2 && !['cancel', 'delete', 'close', 'vote'].includes(parts[2])) {
                    sessionId = parts[2];
                }
            }
            let sessions = JSON.parse(localStorage.getItem('bgg_mock_sessions') || '[]');
            sessions = sessions.filter(s => s.session_id !== sessionId);
            localStorage.setItem('bgg_mock_sessions', JSON.stringify(sessions));
            data = { message: "Session deleted successfully", session_id: sessionId };
        } else if (endpoint.startsWith('/session') && (!options.method || options.method === 'GET')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            const sessionId = urlParams.get('session_id') || urlParams.get('id');
            const sessions = JSON.parse(localStorage.getItem('bgg_mock_sessions') || '[]');
            let found = sessions.find(s => s.session_id === sessionId);
            if (!found && sessions.length > 0 && (!sessionId || sessionId === 'demo')) {
                found = sessions[0];
            }
            if (found) {
                const now = new Date();
                if (found.closes_at) found.is_closed = now >= new Date(found.closes_at);
                if (found.creator_name === 'anonymous_host') {
                    found.creator_name = (window.Auth && window.Auth.getBggUsername && window.Auth.getBggUsername()) || 'Host';
                }
                data = found;
            } else {
                data = { error: "Session not found" };
            }
        } else if (endpoint.startsWith('/session') && options.method === 'POST') {
            const payload = JSON.parse(options.body || '{}');
            const now = new Date();
            const durationHours = parseFloat(payload.duration_hours || 24);
            const closesAt = new Date(now.getTime() + durationHours * 3600 * 1000).toISOString();
            const newSession = {
                session_id: Math.random().toString(36).substring(2, 10),
                creator_id: payload.creator_id || payload.creator_name || 'Host',
                creator_name: payload.creator_name || payload.creator_id || 'Host',
                group_name: payload.group_name || 'Friday Game Night',
                created_at: now.toISOString(),
                closes_at: closesAt,
                duration_hours: durationHours,
                candidates: payload.candidates || [],
                roster: payload.roster || [],
                votes: {},
                is_closed: false,
                consensus: {
                    total_voters: 0,
                    winner: payload.candidates && payload.candidates.length ? payload.candidates[0] : null,
                    rankings: (payload.candidates || []).map(c => ({ id: String(c.id), name: c.name, score: 0, yes_count: 0, neutral_count: 0, veto_count: 0, is_vetoed: false, candidate: c })),
                    vetoed_games: []
                }
            };
            const sessions = JSON.parse(localStorage.getItem('bgg_mock_sessions') || '[]');
            sessions.unshift(newSession);
            localStorage.setItem('bgg_mock_sessions', JSON.stringify(sessions));
            data = newSession;
        } else if (endpoint.startsWith('/cafe/validate-bgg')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            const username = (urlParams.get('username') || '').trim();
            if (!username) {
                return {
                    ok: false,
                    status: 400,
                    json: async () => ({ error: "username query parameter is required" })
                };
            }
            if (username.toLowerCase() === 'nonexistent') {
                return {
                    ok: false,
                    status: 404,
                    json: async () => ({ error: "User does not exist on BoardGameGeek" })
                };
            }
            data = {
                status: "success",
                username: username,
                total_owned: 580,
                shelf_tags_detected: 412,
                sample_matches: [
                    { id: "13", name: "Catan", raw_comment: "Shelf A-1 (Gateway)", extracted_location: "A-1" },
                    { id: "266192", name: "Wingspan", raw_comment: "Location: B-3", extracted_location: "B-3" },
                    { id: "342942", name: "Ark Nova", raw_comment: "Shelf C-2 [Heavy]", extracted_location: "C-2" },
                    { id: "366013", name: "Sky Team", raw_comment: "Bin 4 (2-Player)", extracted_location: "4" }
                ],
                shelf_regex: "(?:Shelf|Location|Bin):?\\s*([A-Za-z0-9\\-]+)"
            };
        } else if (endpoint.startsWith('/cafe/check-slug')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            const slug = (urlParams.get('slug') || '').trim().toLowerCase();
            const takenSlugs = ['taken-slug', 'the-dice-box-official'];
            data = {
                available: !takenSlugs.includes(slug),
                slug: slug
            };
        } else if (endpoint.startsWith('/cafe/onboard') && options.method === 'POST') {
            const payload = JSON.parse(options.body || '{}');
            const cafeId = payload.cafe_id || payload.slug || 'my-cafe';
            const savedItem = {
                ...payload,
                cafe_id: cafeId,
                slug: cafeId,
                created_at: new Date().toISOString()
            };
            delete savedItem.staff_pin;
            localStorage.setItem('bgg_mock_cafe_' + cafeId, JSON.stringify(savedItem));
            data = {
                status: "success",
                message: "Venue successfully registered",
                cafe: savedItem
            };
        } else if (endpoint.startsWith('/cafe/meta')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            const cafeId = urlParams.get('cafe_id') || urlParams.get('slug') || 'demo-cafe';
            const saved = JSON.parse(localStorage.getItem('bgg_mock_cafe_' + cafeId) || 'null');
            data = saved || {
                cafe_id: cafeId,
                name: "The Malt & Meeple Cafe",
                slug: cafeId,
                bgg_username: "maltandmeeple",
                table_count: 20,
                wifi_ssid: "Malt-Guest",
                wifi_password: "rollinitiative",
                tagline: "Craft beer & tabletop games in downtown.",
                drink_pairings_enabled: true
            };
        } else if (endpoint.startsWith('/cafe/sync')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            let cafeId = urlParams.get('cafe_id');
            if (!cafeId && options.body) {
                try {
                    const parsedBody = JSON.parse(options.body);
                    cafeId = parsedBody.cafe_id;
                } catch(e) {}
            }
            cafeId = cafeId || 'demo-cafe';
            const saved = JSON.parse(localStorage.getItem('bgg_mock_cafe_' + cafeId) || '{}');
            const nowIso = new Date().toISOString();
            saved.last_sync_timestamp = nowIso;
            localStorage.setItem('bgg_mock_cafe_' + cafeId, JSON.stringify(saved));
            data = {
                status: "success",
                message: `Sync job successfully enqueued for cafe "${cafeId}".`,
                cafe_id: cafeId,
                bgg_username: saved.bgg_username || "maltandmeeple",
                last_sync_timestamp: nowIso
            };
        } else if (endpoint.startsWith('/cafe/my-cafes')) {
            const cafes = [];
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                if (k.startsWith('bgg_mock_cafe_')) {
                    try {
                        const item = JSON.parse(localStorage.getItem(k));
                        if (item && item.cafe_id) cafes.push(item);
                    } catch (e) {}
                }
            }
            if (cafes.length === 0) {
                const defaultCafe = {
                    cafe_id: "the-malt-and-meeple",
                    name: "The Malt & Meeple Cafe",
                    slug: "the-malt-and-meeple",
                    bgg_username: "maltandmeeple",
                    table_count: 20,
                    wifi_ssid: "MaltMeeple-Guest",
                    wifi_password: "rollinitiative",
                    tagline: "24 craft beers on tap & 600+ tabletop games. Ask staff for recommendations!",
                    shelf_regex: "(?:Shelf|Location|Bin):?\\s*([A-Za-z0-9\\-]+)",
                    drink_pairings_enabled: true,
                    last_sync_timestamp: new Date().toISOString()
                };
                localStorage.setItem('bgg_mock_cafe_the-malt-and-meeple', JSON.stringify(defaultCafe));
                cafes.push(defaultCafe);
            }
            data = {
                status: "success",
                cafes: cafes
            };
        } else if (endpoint.startsWith('/cafe/update') && options.method === 'POST') {
            const payload = JSON.parse(options.body || '{}');
            const cafeId = (payload.cafe_id || 'the-malt-and-meeple').toLowerCase();
            const existing = JSON.parse(localStorage.getItem('bgg_mock_cafe_' + cafeId) || '{}');
            const updated = {
                ...existing,
                ...payload,
                cafe_id: cafeId,
                updated_at: new Date().toISOString()
            };
            delete updated.staff_pin;
            localStorage.setItem('bgg_mock_cafe_' + cafeId, JSON.stringify(updated));
            data = {
                status: "success",
                message: "Cafe settings updated successfully",
                cafe: updated
            };
        } else if (endpoint.startsWith('/collection')) {
            const urlParams = new URLSearchParams(endpoint.split('?')[1] || '');
            const username = (urlParams.get('username') || '').toLowerCase();
            if (!username || username.startsWith('invalid') || username === 'ghost_user' || username === 'unknown_player') {
                const errXml = `<?xml version="1.0" encoding="utf-8"?><errors><error><message>Invalid username specified</message></error></errors>`;
                return {
                    ok: false,
                    status: 400,
                    text: async () => errXml,
                    json: async () => ({ error: "Invalid username" })
                };
            }
            const sampleXml = `<?xml version="1.0" encoding="utf-8"?>
            <items totalitems="2" termsofuse="https://boardgamegeek.com/xmlapi/termsofuse" pubdate="Fri, 28 Aug 2026 12:00:00 +0000">
                <item objectid="174430" subtype="boardgame" collid="1">
                    <name sortindex="1">Gloomhaven</name>
                    <yearpublished>2017</yearpublished>
                    <thumbnail>https://cf.geekdo-images.com/sZYp_3BTDGjh2XdAnAqBulk_thumb.jpg</thumbnail>
                    <status own="1" prevowned="0" fortrade="0" want="0" wanttoplay="0" wanttobuy="0" wishlist="0"/>
                    <stats minplayers="1" maxplayers="4" minplaytime="60" maxplaytime="120" playingtime="120" numowned="50000">
                        <rating value="9"><bayesaverage value="8.4"/></rating>
                    </stats>
                </item>
                <item objectid="266192" subtype="boardgame" collid="2">
                    <name sortindex="1">Wingspan</name>
                    <yearpublished>2019</yearpublished>
                    <thumbnail>https://cf.geekdo-images.com/yLZJ0aJR-_liNq0Azxhl0Ew_thumb.jpg</thumbnail>
                    <status own="1" prevowned="0" fortrade="0" want="0" wanttoplay="0" wanttobuy="0" wishlist="0"/>
                    <stats minplayers="1" maxplayers="5" minplaytime="40" maxplaytime="70" playingtime="70" numowned="80000">
                        <rating value="8"><bayesaverage value="8.1"/></rating>
                    </stats>
                </item>
            </items>`;
            return {
                ok: true,
                status: 200,
                text: async () => sampleXml,
                json: async () => ({ totalitems: 2 })
            };
        } else if (endpoint.startsWith('/similar')) {
            data = {
                similar_games: [
                    { id: "224517", name: "Gloomhaven", similarity: 0.88, rating: 8.7, complexity: 4.4 },
                    { id: "266192", name: "Wingspan", similarity: 0.76, rating: 8.1, complexity: 2.4 }
                ]
            };
        } else {
            data = {};
        }
        
        if (endpoint.startsWith('/preferences') && data && data.bgg_username) {
            window.Auth.setBggUsername(data.bgg_username);
        }

        return {
            ok: true,
            status: 200,
            json: async () => data,
            text: async () => typeof data === 'string' ? data : JSON.stringify(data)
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
    
    const response = await fetch(url, options);
    
    // Auto-sync preferences bgg_username if fetched
    if (endpoint.startsWith('/preferences') && response.ok && options.method !== 'DELETE') {
        response.clone().json().then(prefData => {
            if (prefData && prefData.bgg_username) {
                window.Auth.setBggUsername(prefData.bgg_username);
            }
        }).catch(() => {});
    }

    return response;
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

    const thumbUrl = rec.thumbnail || "https://cf.geekdo-images.com/images/placeholder_thumb.png";
    const loadingClass = isPending ? "loading" : "";
    const yearHtml = rec.year_published ? `<span class="badge year-badge" title="Year Published">${rec.year_published}</span>` : "";
    
    const affinitiesHtml = (function() {
        if (!rec.member_affinities || Object.keys(rec.member_affinities).length === 0) {
            return "";
        }
        let html = `<div class="member-affinities-container">`;
        html += `<div class="member-affinities-title">Group Member Taste Alignment:</div>`;
        html += `<div class="member-affinities-list">`;
        
        Object.entries(rec.member_affinities).forEach(([user, val]) => {
            // Scale cosine similarity (which maxes around 0.60 due to dimensionality differences) to a 0-100% display scale
            const displayPct = Math.min(100, Math.max(0, Math.round((val / 0.60) * 100)));
            
            // Dynamic color determination based on percentage thresholds
            let barColor = "linear-gradient(90deg, #ef4444, #f87171)"; // Crimson/Red for <40%
            if (displayPct >= 70) {
                barColor = "linear-gradient(90deg, #10b981, #34d399)"; // Emerald/Green for >=70%
            } else if (displayPct >= 40) {
                barColor = "linear-gradient(90deg, #f59e0b, #fbbf24)"; // Amber/Yellow for 40-70%
            }
            
            html += `
                <div class="member-affinity-row">
                    <span class="member-affinity-name">${window.escapeHTML(user)}</span>
                    <div class="member-affinity-bar-track">
                        <div class="member-affinity-bar-fill" style="width: ${displayPct}%; background: ${barColor};"></div>
                    </div>
                    <span class="member-affinity-value">${displayPct}%</span>
                </div>
            `;
        });
        
        html += `</div></div>`;
        return html;
    })();

    return `
        <div class="rec-card" style="animation-delay: ${index * 0.05}s;">
            <div class="rec-card-body">
                <div class="rec-card-thumbnail">
                    <img src="${thumbUrl}" alt="${window.escapeHTML(rec.name)}" loading="lazy" onerror="this.onerror=null; this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png';">
                </div>
                <div class="rec-card-content">
                    <div class="rec-card-header">
                        <a href="${gameLink}" target="_blank" class="rec-title">${window.escapeHTML(rec.name)}</a>
                        ${yearHtml}
                    </div>
                    <div class="rec-stats-container">
                        ${statsHtml}
                    </div>
                </div>
            </div>
            <p class="rec-reason ${loadingClass}" data-game-id="${rec.id || ''}">${window.escapeHTML(rec.reason)}</p>
            ${affinitiesHtml}
        </div>
    `;
};

// Render Skeleton Cards placeholder
window.renderSkeletonCards = function(container, count = 4) {
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `
            <div class="rec-card skeleton-card-placeholder">
                <div class="rec-card-body" style="display: flex; gap: 16px; flex-direction: row; align-items: flex-start;">
                    <div class="skeleton skeleton-avatar" style="width: 76px; height: 76px; border-radius: 12px; flex-shrink: 0;"></div>
                    <div class="rec-card-content" style="flex-grow: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0;">
                        <div class="rec-card-header" style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; width: 100%;">
                            <div class="skeleton skeleton-text title" style="width: 60%; height: 20px; margin: 0;"></div>
                            <div class="skeleton skeleton-text" style="width: 48px; height: 20px; border-radius: 9999px; margin: 0;"></div>
                        </div>
                        <div class="rec-stats-container" style="display: flex; gap: 6px; margin-top: 2px; margin-bottom: 4px; flex-wrap: wrap;">
                            <div class="skeleton skeleton-text" style="width: 55px; height: 22px; border-radius: 6px; margin: 0;"></div>
                            <div class="skeleton skeleton-text" style="width: 70px; height: 22px; border-radius: 6px; margin: 0;"></div>
                            <div class="skeleton skeleton-text" style="width: 85px; height: 22px; border-radius: 6px; margin: 0;"></div>
                        </div>
                    </div>
                </div>
                <div class="skeleton skeleton-text paragraph" style="width: 100%; height: 42px; border-radius: 6px; margin-top: 10px;"></div>
            </div>
        `;
    }
    container.innerHTML = html;
};
