"""
Bedrock LLM narration module for the BGG Recommender.

Handles prompt construction, Bedrock Converse API calls,
response parsing, and name-to-ID mapping for AI-generated recommendation reasons.
"""
import os
import json

import boto3
import pandas as pd

from cache_utils import logger, safe_list, build_game_metadata

# Initialize Bedrock client
_default_bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-micro-v1:0')

def _bedrock():
    try:
        import bgg_recommender
        if 'bedrock' in bgg_recommender.__dict__:
            return bgg_recommender.__dict__['bedrock']
    except (ImportError, AttributeError):
        pass
    return _default_bedrock

def __getattr__(name):
    """
    Dynamic attribute loader for bedrock to support test patching of bgg_recommender.bedrock.
    """
    if name == 'bedrock':
        return _bedrock()
    raise AttributeError(f"module {__name__} has no attribute {name}")


def format_personality_context(personality_answers):
    """
    Formats the user's personality quiz choices into a natural-language playstyle description.
    """
    if not personality_answers or not isinstance(personality_answers, dict):
        return "- Playstyle preferences: Balanced modern board games across mechanics and themes."

    lines = []
    fmt = personality_answers.get('format')
    if fmt == 'cooperative':
        lines.append("- Format Preference: Cooperative gameplay (working together as a team against the board)")
    elif fmt == 'competitive':
        lines.append("- Format Preference: Competitive head-to-head strategy")

    comp = personality_answers.get('complexity')
    if comp == 'light':
        lines.append("- Complexity Preference: Lightweight and accessible (easy to learn, breezy rules)")
    elif comp == 'medium':
        lines.append("- Complexity Preference: Medium-weight tactical depth (rewarding strategy without steep learning curves)")
    elif comp == 'heavy':
        lines.append("- Complexity Preference: Heavy brain-burner strategy (deep systems, complex decision trees)")

    dur = personality_answers.get('duration')
    if dur == 'short':
        lines.append("- Play Time Preference: Quick sessions (30-45 minutes)")
    elif dur == 'medium':
        lines.append("- Play Time Preference: Standard game night length (45-90 minutes)")
    elif dur == 'long':
        lines.append("- Play Time Preference: Epic, immersive sessions (90+ minutes)")

    theme = personality_answers.get('theme')
    if theme == 'nature':
        lines.append("- Theme Preference: Wildlife, nature, animals, and environmental worldbuilding")
    elif theme == 'scifi':
        lines.append("- Theme Preference: Sci-Fi, fantasy, and heroic adventure")
    elif theme == 'economic':
        lines.append("- Theme Preference: Economic growth, historical development, and industry building")

    luck = personality_answers.get('luck')
    if luck == 'high':
        lines.append("- Luck Preference: High excitement, dice rolling, and tactical adaptability")
    elif luck == 'low':
        lines.append("- Luck Preference: Low-luck deterministic strategy and pure player agency")

    style = personality_answers.get('style')
    if style == 'engine':
        lines.append("- Mechanism Preference: Engine building, deck building, and satisfying card combos")
    elif style == 'worker':
        lines.append("- Mechanism Preference: Worker placement, action drafting, and area control")

    inter = personality_answers.get('interaction')
    if inter == 'conflict':
        lines.append("- Interaction Style: Direct player conflict, area competition, and tactical attacks")
    elif inter == 'social':
        lines.append("- Interaction Style: Social negotiation, trading, bluffing, and table talk")
    elif inter == 'solitaire':
        lines.append("- Interaction Style: Multi-path puzzle solving, hand management, and low direct conflict")

    return "\n".join(lines) if lines else "- Playstyle preferences: Balanced modern board games."


def narrate_recommendations(top_candidates, liked_games_str, weight_context, query_params,
                            is_inline=False, inline_weights=None, inline_profile=None):
    """
    Calls Bedrock to generate personalized 1-sentence reasons for each recommendation.

    Args:
        top_candidates: List of candidate row dicts (from scoring.score_candidates).
        liked_games_str: Formatted string of user's liked games for the prompt.
        weight_context: Formatted string of user's weight preferences for the prompt.
        query_params: Original query parameters dict.
        is_inline: Whether request is an inline/wizard request.
        inline_weights: Dict of inline weights including optional personality_answers.
        inline_profile: Optional list of inline ratings dicts.

    Returns:
        List of recommendation dicts with 'name', 'reason', 'id', and rich metadata.
        Returns None if Bedrock invocation fails entirely.
    """
    # Build candidates string for the prompt
    candidates_str = ""
    if top_candidates:
        cand_list = []
        for row in top_candidates:
            cats = ", ".join(safe_list(row.get('categories')))
            mechs = ", ".join(safe_list(row.get('mechanics')))

            players_str = (
                f"Players: {row['min_players']}-{row['max_players']}"
                if 'min_players' in row and 'max_players' in row and pd.notna(row['min_players'])
                else f"Max Players: {row.get('max_players', 'N/A')}"
            )
            playtime_str = f", Playtime: {row['playing_time']}m" if 'playing_time' in row and pd.notna(row['playing_time']) else ""
            complexity_str = f", Complexity: {row['complexity']:.1f}/5" if 'complexity' in row and pd.notna(row['complexity']) else ""
            designers_list = safe_list(row.get('designers'))
            designers_str = f", Designers: {', '.join(designers_list)}" if 'designers' in row and designers_list else ""

            cand_list.append(
                f"- {row['name']} (Year: {row.get('year_published', 'N/A')}, Rating: {row.get('rating', 'N/A')}, "
                f"{players_str}{playtime_str}{complexity_str}{designers_str}, Categories: {cats}, Mechanics: {mechs})"
            )
        candidates_str = "\n".join(cand_list)

    # Determine prompt mode: Personality Test, Quick Taste Test, or Collection Profile
    if is_inline and inline_weights and not liked_games_str:
        # Casual Personality Test user (no rated games, purely quiz answers)
        personality_answers = inline_weights.get('personality_answers') if isinstance(inline_weights, dict) else None
        personality_desc = format_personality_context(personality_answers)
        user_prompt = f"""You are a board game recommendation expert.
     
The user is a new board game player who completed a playstyle preference quiz with the following declared preferences:
{personality_desc}
{weight_context}
Please recommend 10 board games for the user.
"""
        explanation_instructions = """For each recommended game:
1. Provide the exact name of the game.
2. Provide a punchy, direct 1-sentence explanation of why they will love playing it (aim for 12–15 words, maximum 18 words). Explain how the game delivers on their declared playstyle preferences (e.g. cooperative teamwork, engine-building satisfaction, strategic worker placement, or thematic immersion). Do NOT mention collection or ownership history. Use active verbs and highlight concrete mechanics or gameplay dynamics. Rotate through distinct framing angles across the 10 recommendations. No two recommendations may begin with the same word or phrase."""

    elif is_inline and liked_games_str:
        # Quick Taste Test user (liked seed games and write-in favorites)
        user_prompt = f"""You are a board game recommendation expert.
     
The user recently completed a Quick Taste Test and indicated they enjoy the following board games:
{liked_games_str}
{weight_context}
Please recommend 10 board games for the user.
"""
        explanation_instructions = """For each recommended game:
1. Provide the exact name of the game.
2. Provide a punchy, direct 1-sentence explanation of why they will love playing it (aim for 12–15 words, maximum 18 words). Directly connect the recommended game to 1 or 2 specific titles they liked above, highlighting shared mechanics (e.g. tile drafting, card combos, resource management), pacing, or tactical feel. Use active verbs and direct comparisons. Rotate through distinct framing angles across the 10 recommendations. No two recommendations may begin with the same word or phrase."""

    else:
        # Standard BGG User Profile (collection games with ratings)
        user_prompt = f"""You are a board game recommendation expert.
     
The user has the following board games in their collection with their ratings (where higher is better):
{liked_games_str if liked_games_str else "- No games rated/owned yet."}
{weight_context}
Please recommend 10 board games for the user.
"""
        explanation_instructions = """For each recommended game:
1. Provide the exact name of the game.
2. Provide a punchy, direct 1-sentence explanation of why they will love playing it (aim for 12–15 words, maximum 18 words). Directly connect the recommended game to 1 or 2 specific board games they already like or own from their list above, referencing shared mechanics, strategic dynamics, or thematic elements. Use active verbs and avoid filler phrases. Rotate through distinct framing angles across the 10 recommendations (e.g. mechanical alignment, thematic resonance, player count fit, pacing, complexity balance, or designer lineage). No two recommendations may begin with the same word or phrase. If specific play time or complexity preferences are provided, also mention how this game fits those preferences."""

    if candidates_str:
        user_prompt += f"""
Here is a list of candidate board games from our catalog that match the user's preferences:
{candidates_str}

Please select the best 10 games from the candidates list above. Do NOT select games that are not in the candidates list.
Review the candidate list for variants, new editions, or implementations of the same game family (e.g., base game vs 2nd edition vs reimplementation). Deduplicate these and only output the most relevant or highest-ranked edition in your final 10 recommendations.
"""
    else:
        user_prompt += """
Please recommend 10 great board games from your general knowledge.
"""

    user_prompt += f"""
{explanation_instructions}

Format your response as a JSON object with a single key "recommendations", which is a list of objects containing "name" and "reason".
Do not include any introductory or concluding text (e.g. do not say "Here are your recommendations:" or use markdown code blocks). Output only raw, valid JSON.
"""

    try:
        messages = [
            {
                "role": "user",
                "content": [{"text": user_prompt}]
            }
        ]

        system_prompts = [
            {
                "text": "You are a board game recommendation expert. Your job is to select the best games and write punchy, direct, and engaging 1-sentence explanations (aim for 12–15 words per reason, maximum 18 words). Use active verbs and highlight concrete mechanics, pacing, or thematic dynamics. Avoid generic filler (e.g., do NOT start sentences with 'If you enjoyed...', 'This game is perfect for...', or 'A great choice because...'). Do NOT hallucinate themes or mechanics that are not explicitly present in the provided context lists. Ensure you output raw, valid JSON matching the requested schema."
            }
        ]

        logger.info(f"Calling Bedrock Converse API with model {bedrock_model_id}...")
        response = _bedrock().converse(
            modelId=bedrock_model_id,
            messages=messages,
            system=system_prompts,
            inferenceConfig={
                "maxTokens": 1200,
                "temperature": 0.6
            }
        )

        response_text = response['output']['message']['content'][0]['text'].strip()
        logger.info(f"Received Bedrock response: {response_text}")

        # Clean up response text if wrapped in markdown blocks
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                lines = lines[1:-1]
            response_text = "\n".join(lines).strip()

        result_json = json.loads(response_text)

        # Map names back to IDs from the candidates/catalog
        candidate_map = {row['name'].lower(): row for row in top_candidates}
        final_recs = []
        recommended_ids = set()
        original_count = len(result_json.get('recommendations', []))

        for rec in result_json.get('recommendations', []):
            rec_name = rec.get('name', '')
            game_meta = candidate_map.get(rec_name.lower())

            # Partial match fallback for LLM naming tweaks
            if not game_meta:
                for cand_name, cand_row in candidate_map.items():
                    if rec_name.lower() in cand_name or cand_name in rec_name.lower():
                        game_meta = cand_row
                        break

            if game_meta and str(game_meta['id']) not in recommended_ids:
                rec_id = str(game_meta['id'])
                recommended_ids.add(rec_id)
                metadata = build_game_metadata(game_meta)
                metadata['reason'] = rec.get('reason', '')
                metadata['name'] = game_meta['name']  # Normalize to catalog name
                final_recs.append(metadata)
            else:
                logger.warning(f"Excluding recommended game '{rec_name}' as it was not in top candidates list (or was duplicated).")

        # Fill in up to 10 from top candidates if the LLM output fewer valid ones
        if len(final_recs) < 10 and original_count >= 8:
            for row in top_candidates:
                if len(final_recs) >= 10:
                    break
                cand_id = str(row['id'])
                if cand_id not in recommended_ids:
                    recommended_ids.add(cand_id)
                    reason_mechs = ", ".join(safe_list(row.get('mechanics'))[:3])
                    metadata = build_game_metadata(row)
                    metadata['reason'] = f"Highly ranked catalog match sharing key mechanics: {reason_mechs}."
                    final_recs.append(metadata)

        return final_recs

    except Exception as bedrock_e:
        logger.error(f"Bedrock invocation or parsing failed: {bedrock_e}")
        return None


def build_fallback_recommendations(top_candidates):
    """
    Returns scored candidates with generic reason strings as a fallback
    when Bedrock narration is unavailable or not requested.
    """
    recs = []
    for row in top_candidates[:10]:
        reason_mechs = ", ".join(safe_list(row.get('mechanics'))[:3])
        metadata = build_game_metadata(row)
        metadata['reason'] = f"Highly recommended match sharing mechanics: {reason_mechs}."
        recs.append(metadata)
    return recs


def build_weight_context(query_params, weights):
    """
    Builds the weight context string for the Bedrock prompt from query parameters and parsed weights.
    """
    w_mech = weights.get('w_mech', 0.5)
    w_cat = weights.get('w_cat', 0.5)
    w_pop = weights.get('w_pop', 0.5)
    w_hot = weights.get('w_hot', 0.0)
    w_comp = weights.get('w_comp', 0.4)
    w_des = weights.get('w_des', 0.3)
    w_pub = weights.get('w_pub', 0.1)
    player_count = query_params.get('player_count')
    duration_pref = query_params.get('duration_pref', 'any').lower()
    complexity_pref = query_params.get('complexity_pref', 'any').lower()

    weight_context = f"""
The user has tuned their preference weights for similarity scoring as follows:
- Mechanics Similarity Weight: {w_mech * 100:.0f}%
- Categories Similarity Weight: {w_cat * 100:.0f}%
- Popularity/Community Rating Weight: {w_pop * 100:.0f}%
- Hotness/Trending Weight: {w_hot * 100:.0f}%
- Complexity Similarity Weight: {w_comp * 100:.0f}%
- Designer Similarity Weight: {w_des * 100:.0f}%
- Publisher Similarity Weight: {w_pub * 100:.0f}%
"""
    if player_count:
        weight_context += f"- Target Session Player Count: {player_count} players (all candidate games support this player count)\n"
    if duration_pref and duration_pref != 'any':
        weight_context += f"- Target Play Time Preference: {duration_pref.capitalize()} length games\n"
    if complexity_pref and complexity_pref != 'any':
        weight_context += f"- Target Complexity/Weight Preference: {complexity_pref.capitalize()} weight games\n"
    if w_hot > 0.4:
        weight_context += "The user is highly interested in currently trending or hot releases.\n"
    if w_mech > 0.7:
        weight_context += "The user places strong emphasis on games sharing similar play styles and mechanics.\n"
    if w_cat > 0.7:
        weight_context += "The user places strong emphasis on games sharing similar themes and categories.\n"

    return weight_context
