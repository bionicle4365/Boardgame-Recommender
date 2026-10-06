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
bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')

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


def estimate_teach_time(row):
    """
    Estimates rules teach time in minutes based on complexity and game metadata.
    """
    if row.get('teach_time'):
        return str(row['teach_time'])
    
    comp = row.get('complexity')
    if comp is None or (isinstance(comp, float) and pd.isna(comp)):
        return "5-10 mins"
    try:
        c = float(comp)
        if c < 1.8:
            return "3-5 mins"
        elif c < 2.5:
            return "5-10 mins"
        elif c < 3.3:
            return "10-15 mins"
        elif c < 4.0:
            return "15-25 mins"
        else:
            return "25-40 mins"
    except (ValueError, TypeError):
        return "5-10 mins"


def build_cafe_sommelier_prompt(top_candidates, vibe=None, query_params=None, cafe_name=None):
    """
    Constructs a dedicated Bedrock prompt for cafe tables acting as a knowledgeable board game sommelier / guru.
    Emphasizes rules teach ease, group dynamics, table atmosphere over drinks, shelf location, and vibe match.
    """
    query_params = query_params or {}
    player_count = query_params.get('player_count')
    duration_pref = query_params.get('duration_pref', 'any')
    table = query_params.get('table')
    venue = cafe_name or "our board game cafe"

    vibe_descriptions = {
        'party': 'Party & Social / Icebreaker (high energy, laughing, minimal rules)',
        'casual_strategy': 'Casual Strategy & Chill (satisfying decisions without high stress)',
        'deep_strategy': 'Deep Strategy & Brain-Burner (rewarding engine building and complex tactics)',
        'cooperative': 'Cooperative & Teamwork (players working together against the board)',
        'direct_conflict': 'Competitive & Take-That (high interaction, battles, and rivalry)'
    }
    vibe_desc = vibe_descriptions.get(str(vibe or '').lower(), 'Engaging modern board games tailored for the table')

    cand_lines = []
    for row in top_candidates:
        name = row.get('name', 'Unknown')
        comp = f"{float(row['complexity']):.1f}/5" if pd.notna(row.get('complexity')) else "N/A"
        playtime = f"{row.get('playing_time')}m" if pd.notna(row.get('playing_time')) else "N/A"
        p_min = row.get('min_players', '')
        p_max = row.get('max_players', '')
        players_str = f"{p_min}-{p_max}" if p_min and p_max else f"Max {p_max or 'N/A'}"
        teach = estimate_teach_time(row)
        shelf = row.get('shelf_location') or row.get('shelf') or ''
        shelf_str = f", Shelf: {shelf}" if shelf else ""
        cats = ", ".join(safe_list(row.get('categories'))[:3])
        mechs = ", ".join(safe_list(row.get('mechanics'))[:3])

        cand_lines.append(
            f"- {name} (Complexity: {comp}, Players: {players_str}, Playtime: {playtime}, Teach: {teach}{shelf_str}, Categories: {cats}, Mechanics: {mechs})"
        )
    candidates_str = "\n".join(cand_lines)

    table_info = f"at Table {table} " if table else ""
    user_prompt = f"""You are the head board game sommelier and table guru at {venue}.
A group of patrons {table_info}is looking for the perfect game for their session right now.

Session Parameters:
- Player Count: {player_count if player_count else 'Flexible'}
- Target Vibe: {vibe_desc}
- Session Length Preference: {duration_pref.capitalize() if duration_pref != 'any' else 'Flexible'}

Here is the list of games currently available in our cafe library matching their table size:
{candidates_str}

Please select the best 10 games from the candidates list above for their table. Do NOT recommend games that are not in this list.

For each recommended game:
1. Provide the exact name of the game.
2. Write an enthusiastic, knowledgeable 1–2 sentence recommendation in a friendly sommelier guru voice (aim for 20–28 words, maximum 32 words).
   Explain why this game is a blast for their table tonight: emphasize how easy it is to teach over drinks, how the gameplay mechanics spark fun interaction or satisfying strategy, and why it fits their chosen vibe.
   Vary your opening phrases across recommendations. Do NOT start multiple recommendations with the same word.

Format your response as a JSON object with a single key "recommendations", which is a list of objects containing "name" and "reason".
Do not include any introductory or concluding text (e.g. do not say "Here are your recommendations:" or use markdown code blocks). Output only raw, valid JSON.
"""
    return user_prompt


def narrate_recommendations(top_candidates, liked_games_str, weight_context, query_params,
                            is_inline=False, inline_weights=None, inline_profile=None,
                            cafe_id=None, vibe=None, table=None, cafe_name=None):
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
        cafe_id: Optional cafe BGG username / ID when in cafe mode.
        vibe: Optional table vibe preset (party, casual_strategy, etc.).
        table: Optional table number string.
        cafe_name: Optional display name of the cafe.

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

            # Attached linkages from scoring.attach_candidate_linkages
            linkage_parts = []
            if row.get('matched_favorites'):
                linkage_parts.append(f"Similar to favorite: {', '.join(row['matched_favorites'])}")
            if row.get('key_shared_mechanics'):
                linkage_parts.append(f"Shared mechanics: {', '.join(row['key_shared_mechanics'])}")
            if row.get('best_players'):
                linkage_parts.append(f"Best player count: {row['best_players']}")
            linkage_str = f" | {'; '.join(linkage_parts)}" if linkage_parts else ""

            cand_list.append(
                f"- {row['name']} (Year: {row.get('year_published', 'N/A')}, Rating: {row.get('rating', 'N/A')}, "
                f"{players_str}{playtime_str}{complexity_str}{designers_str}, Categories: {cats}, Mechanics: {mechs}{linkage_str})"
            )
        candidates_str = "\n".join(cand_list)

    if cafe_id:
        user_prompt = build_cafe_sommelier_prompt(
            top_candidates, vibe=vibe, query_params=query_params, cafe_name=cafe_name or cafe_id
        )
    # Determine prompt mode: Personality Test, Quick Taste Test, or Collection Profile
    elif is_inline and inline_weights and not liked_games_str:
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
2. Provide an engaging 1–2 sentence recommendation in a knowledgeable sommelier voice (aim for 20–28 words, maximum 32 words). Explain how the game delivers on their declared playstyle preferences (e.g. cooperative teamwork, engine-building satisfaction, strategic worker placement, or thematic immersion). Do NOT mention collection or ownership history. Use active verbs and highlight concrete mechanics or gameplay dynamics. Vary your sentence structures across recommendations and do not repeat the same opening phrase."""

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
2. Provide an engaging 1–2 sentence recommendation in a knowledgeable sommelier voice (aim for 20–28 words, maximum 32 words). Directly connect the recommended game to 1 or 2 specific titles they liked above (using the provided similarity linkages), highlighting shared mechanics (e.g. tile drafting, card combos, resource management), pacing, or tactical feel. Use active verbs and direct comparisons. Vary your sentence structures across recommendations and do not repeat the same opening phrase."""

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
2. Provide an engaging 1–2 sentence recommendation in a knowledgeable sommelier voice (aim for 20–28 words, maximum 32 words). Directly connect the recommended game to 1 or 2 specific board games they already like or own from their list above (using the provided similarity linkages), referencing shared mechanics, strategic dynamics, or thematic elements. Use active verbs and avoid filler phrases. Rotate through distinct framing angles across the 10 recommendations (e.g. mechanical alignment, thematic resonance, player count fit, pacing, complexity balance, or designer lineage). No two recommendations may begin with the same word or phrase. If specific play time or complexity preferences are provided, also mention how this game fits those preferences."""

    if not cafe_id:
        if candidates_str:
            user_prompt += f"""
Here is a list of candidate board games from our catalog that match the user's preferences:
{candidates_str}

Please select the best 10 games from the candidates list above. Do NOT select games that are not in the candidates list.
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

        if cafe_id:
            system_prompts = [
                {
                    "text": """You are the lead board game guru and expert sommelier at a lively board game cafe. Your job is to select the 10 best games from the cafe's library and write engaging, welcoming, and persuasive 1–2 sentence recommendations (aim for 20–28 words per reason, maximum 32 words) explaining why each game will be a hit at their table tonight over drinks.

Voice & Style Guidelines:
- Warm, enthusiastic, and approachable table sommelier voice using active verbs.
- Focus on why this game is a blast for their group: ease of learning, satisfying tactile decisions, lively table talk, or dramatic twists.
- Exemplars of excellent recommendations:
  * "Channels quick drafting and vibrant tile-laying with breezy 5-minute rules, making it an instant crowd-pleaser for 4 players over drinks." (21 words)
  * "Offers snappy push-your-luck card play with infectious table banter, delivering big laughs and fast turns without heavy rules overhead." (20 words)
  * "Delivers deep engine-building satisfaction with a crystal-clear rules teach, offering rewarding tactical combos in a brisk 60-minute race." (20 words)
- Keep openings varied across recommendations. Do not repeat the same opening word or pattern.
- Do NOT hallucinate themes, mechanics, or player counts not supported by the provided candidate list.
- Ensure you output raw, valid JSON matching the requested schema."""
                }
            ]
        else:
            system_prompts = [
                {
                    "text": """You are an expert board game sommelier and board game recommendation expert. Your job is to select the best games and write engaging, natural, and persuasive 1–2 sentence recommendations (aim for 20–28 words per reason, maximum 32 words) explaining why the player will love each game.

Voice & Style Guidelines:
- Warm, enthusiastic, and knowledgeable sommelier voice using active verbs.
- Weave favorite game connections and concrete mechanics naturally into each recommendation without formulaic repetition.
- Exemplars of excellent recommendations:
  * "Fans of Wingspan will love the satisfying engine building and tableau crafting, offering rich tactical card combos in a brisk 45-minute race." (22 words)
  * "Channels the tight worker placement of Agricola with a gentler learning curve and high player interaction, making it perfect for 4 players." (23 words)
  * "Delivers on your love for medium-weight strategy, combining snappy card drafting with clever spatial maneuvering on the board." (19 words)
- Keep openings varied across recommendations. Do not repeat the same opening word or pattern.
- Do NOT hallucinate themes, mechanics, or player counts not supported by the provided context.
- Ensure you output raw, valid JSON matching the requested schema."""
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
                metadata['teach_time'] = estimate_teach_time(game_meta)
                if game_meta.get('shelf_location') or game_meta.get('shelf'):
                    metadata['shelf_location'] = game_meta.get('shelf_location') or game_meta.get('shelf')
                if (game_meta.get('rules_video_url') or game_meta.get('video_url')) and not metadata.get('rules_video_url'):
                    metadata['rules_video_url'] = str(game_meta.get('rules_video_url') or game_meta.get('video_url'))
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
                    if cafe_id:
                        metadata['reason'] = f"Great table pick for your group sharing popular cafe mechanics: {reason_mechs}."
                    else:
                        metadata['reason'] = f"Highly ranked catalog match sharing key mechanics: {reason_mechs}."
                    metadata['teach_time'] = estimate_teach_time(row)
                    if row.get('shelf_location') or row.get('shelf'):
                        metadata['shelf_location'] = row.get('shelf_location') or row.get('shelf')
                    if (row.get('rules_video_url') or row.get('video_url')) and not metadata.get('rules_video_url'):
                        metadata['rules_video_url'] = str(row.get('rules_video_url') or row.get('video_url'))
                    final_recs.append(metadata)

        return final_recs

    except Exception as bedrock_e:
        logger.error(f"Bedrock invocation or parsing failed: {bedrock_e}")
        return None


def build_fallback_recommendations(top_candidates, is_cafe=False):
    """
    Returns scored candidates with generic reason strings as a fallback
    when Bedrock narration is unavailable or not requested.
    """
    recs = []
    for row in top_candidates[:10]:
        reason_mechs = ", ".join(safe_list(row.get('mechanics'))[:3])
        metadata = build_game_metadata(row)
        if is_cafe:
            metadata['reason'] = f"Great table pick for your group sharing popular cafe mechanics: {reason_mechs}."
        else:
            metadata['reason'] = f"Highly recommended match sharing mechanics: {reason_mechs}."
        metadata['teach_time'] = estimate_teach_time(row)
        if row.get('shelf_location') or row.get('shelf'):
            metadata['shelf_location'] = row.get('shelf_location') or row.get('shelf')
        if (row.get('rules_video_url') or row.get('video_url')) and not metadata.get('rules_video_url'):
            metadata['rules_video_url'] = str(row.get('rules_video_url') or row.get('video_url'))
        recs.append(metadata)
    return recs


def build_weight_context(query_params, weights):
    """
    Builds the weight context string for the Bedrock prompt from query parameters and parsed weights.
    """
    w_mech = weights.get('w_mech', 0.60)
    w_cat = weights.get('w_cat', 0.40)
    w_pop = weights.get('w_pop', 0.20)
    w_hot = weights.get('w_hot', 0.0)
    w_comp = weights.get('w_comp', 0.35)
    w_des = weights.get('w_des', 0.35)
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
