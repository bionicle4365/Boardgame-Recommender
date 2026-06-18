---
layout: default
title: Home
---

<style>
    .home-container {
        font-family: 'Inter', sans-serif;
    }

    .welcome-banner {
        background: linear-gradient(135deg, #4f46e5 0%, #818cf8 100%);
        border-radius: 20px;
        padding: 48px;
        color: white;
        margin-bottom: 40px;
        box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.2);
    }

    .welcome-banner h1 {
        font-size: 2.5rem;
        font-weight: 800;
        margin-top: 0;
        margin-bottom: 12px;
        font-family: 'Outfit', sans-serif;
    }

    .welcome-banner p {
        font-size: 1.15rem;
        opacity: 0.9;
        margin: 0;
        max-width: 600px;
        line-height: 1.6;
    }

    .features-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 30px;
    }

    @media (min-width: 768px) {
        .features-grid {
            grid-template-columns: 1fr 1fr;
        }
    }

    .feature-card {
        background: white;
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        transition: all 0.3s ease;
        text-decoration: none;
        color: inherit;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }

    .feature-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 20px -8px rgba(0, 0, 0, 0.1);
        border-color: #cbd5e1;
    }

    .feature-icon {
        width: 48px;
        height: 48px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        margin-bottom: 24px;
        font-size: 1.5rem;
    }

    .feature-icon.recommender {
        background: linear-gradient(135deg, #4f46e5 0%, #818cf8 100%);
    }

    .feature-icon.browser {
        background: linear-gradient(135deg, #10b981 0%, #34d399 100%);
    }

    .feature-card h2 {
        margin-top: 0;
        margin-bottom: 12px;
        font-size: 1.5rem;
        font-family: 'Outfit', sans-serif;
        color: var(--text-main);
    }

    .feature-card p {
        color: var(--text-muted);
        margin: 0 0 24px 0;
        line-height: 1.6;
    }

    .card-action {
        font-weight: 600;
        font-size: 0.95rem;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .card-action.recommender {
        color: var(--primary);
    }

    .card-action.browser {
        color: #10b981;
    }
</style>

<div class="home-container">
    <div class="welcome-banner">
        <h1>Boardgame Recommender</h1>
        <p>A smart, AI-powered catalog explorer and recommendation engine. Discover new tabletop experiences tailored to your personal collection, themes, and mechanics.</p>
    </div>

    <div class="features-grid">
        <a href="{{ '/collection/' | relative_url }}" class="feature-card">
            <div>
                <div class="feature-icon browser">🔍</div>
                <h2>BGG Collection Browser</h2>
                <p>Browse, filter, and sort your board game collection directly from BoardGameGeek. Filter by player counts, ratings, and category details.</p>
            </div>
            <div class="card-action browser">
                <span>Browse Collection</span> →
            </div>
        </a>

        <a href="{{ '/recommender/' | relative_url }}" class="feature-card">
            <div>
                <div class="feature-icon recommender">🤖</div>
                <h2>AI Recommendations</h2>
                <p>Get personalized game recommendations powered by Amazon Bedrock (Claude 3 Haiku). Leverages Jaccard similarity to discover new matches.</p>
            </div>
            <div class="card-action recommender">
                <span>Get Recommendations</span> →
            </div>
        </a>
    </div>
</div>
